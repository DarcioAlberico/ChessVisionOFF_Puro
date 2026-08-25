"""O documento do editor, afirmado **sem abrir janela** (S-235).

É a regra da Fase 6, e aqui ela é o item inteiro: o que a aba de texto entregava ao salvar era uma
`str`, e toda formatação que se pintasse no widget morreria com ele. O que este arquivo afirma é que
o documento existe fora do `tkinter` -- e que ele reproduz, caractere a caractere, o texto que a aba
já produzia antes de haver formatação nenhuma.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from chess_diagram_ocr.text import documento, rico
from chess_diagram_ocr.text.pagina import (
    BlocoDeDiagrama,
    BlocoDeTexto,
    Coluna,
    LinhaLida,
    PaginaLida,
)


def _texto(conteudo: str, confianca: float = 1.0, procedencia: str = "camada") -> BlocoDeTexto:
    return BlocoDeTexto.de_linhas(
        [LinhaLida(conteudo, (0.0, 0.0, 10.0, 10.0), confianca, procedencia)]  # type: ignore[arg-type]
    )


def _pagina(*blocos: object) -> PaginaLida:
    return PaginaLida(colunas=(Coluna(indice=0, blocos=tuple(blocos)),))  # type: ignore[arg-type]


class TextoDeHojeTests(unittest.TestCase):
    """A trava de não-regressão: o documento novo produz o texto antigo."""

    def test_o_documento_reproduz_o_texto_de_hoje(self) -> None:
        pagina = _pagina(
            _texto("In this position White has a decisive resource."),
            BlocoDeDiagrama(indice=0, bbox=(0.0, 0.0, 50.0, 50.0), confianca=0.9),
            _texto("1...Bxb7 2.Bxb7 Nd7", 0.5, "glifo"),
        )
        esperado = "".join(s.texto for s in documento.segmentos(pagina))
        self.assertEqual(rico.de_pagina(pagina).para_texto(), esperado)

    def test_a_pagina_vazia_da_documento_vazio(self) -> None:
        self.assertEqual(rico.de_pagina(_pagina()).para_texto(), "")

    def test_a_marca_de_diagrama_continua_texto(self) -> None:
        """`[Diagrama N]` é conteúdo, e não um objeto à parte -- é o que a torna movível."""
        diagrama = BlocoDeDiagrama(indice=2, bbox=(0.0, 0.0, 50.0, 50.0))
        doc = rico.de_pagina(_pagina(diagrama))
        self.assertIn("[Diagrama 3]", doc.para_texto())
        self.assertEqual([c.tipo for c in doc.corridas], [rico.DIAGRAMA])
        self.assertEqual(doc.diagramas[0].texto, "[Diagrama 3]")


class ContextoDaCorridaTests(unittest.TestCase):
    def test_a_corrida_sabe_de_que_bloco_veio(self) -> None:
        pagina = _pagina(_texto("primeiro"), _texto("segundo"))
        doc = rico.de_pagina(pagina)
        conteudo = [c for c in doc.corridas if c.tipo == rico.TEXTO]
        self.assertEqual([c.bloco for c in conteudo], [0, 1])
        self.assertEqual(doc.bloco_de(conteudo[1]).texto, "segundo")

    def test_blocos_iguais_nao_compartilham_indice(self) -> None:
        """Dois parágrafos idênticos são dataclasses **iguais**; o índice sai por identidade.

        Casá-los por `==` daria o mesmo índice aos dois -- e a correção do primeiro iria para o
        bloco errado, em silêncio."""
        pagina = _pagina(_texto("igual"), _texto("igual"))
        conteudo = [c for c in rico.de_pagina(pagina).corridas if c.tipo == rico.TEXTO]
        self.assertEqual([c.bloco for c in conteudo], [0, 1])

    def test_o_separador_nao_tem_bloco_nem_procedencia(self) -> None:
        doc = rico.de_pagina(_pagina(_texto("a"), _texto("b")))
        separadores = [c for c in doc.corridas if c.tipo == rico.SEPARADOR]
        self.assertEqual(len(separadores), 1)
        self.assertEqual(separadores[0].bloco, rico.SEM_BLOCO)
        self.assertIsNone(separadores[0].procedencia)
        self.assertIsNone(doc.bloco_de(separadores[0]))

    def test_a_procedencia_vem_do_bloco(self) -> None:
        doc = rico.de_pagina(_pagina(_texto("lido", 0.5, "glifo")))
        self.assertEqual(doc.corridas[0].procedencia, "glifo")

    def test_a_faixa_vem_de_documento_e_nao_e_atributo(self) -> None:
        """Confiança é medida do reconhecimento; atributo é escolha de quem escreve."""
        doc = rico.de_pagina(_pagina(_texto("adivinhado", 0.1, "glifo")))
        corrida = doc.corridas[0]
        self.assertEqual(corrida.faixa, documento.REVISAR)
        self.assertNotIn("faixa", set(rico.Atributos.__dataclass_fields__))
        self.assertTrue(corrida.atributos.padrao)

    def test_o_negrito_da_pagina_vira_atributo(self) -> None:
        """O que a S-237 traz da camada chega ao documento como atributo, e não como tag."""
        bloco = BlocoDeTexto.de_linhas(
            [LinhaLida("Título", (0.0, 0.0, 10.0, 10.0), 1.0, "camada", negrito=True)]
        )
        doc = rico.de_pagina(_pagina(bloco))
        self.assertTrue(doc.corridas[0].atributos.negrito)


class FusaoTests(unittest.TestCase):
    """Sem a fusão, digitar é o que estraga o documento: uma corrida por tecla."""

    def test_corridas_iguais_se_fundem(self) -> None:
        partido = [rico.Corrida(texto=letra) for letra in "palavra"]
        self.assertEqual(rico.fundir(partido), (rico.Corrida(texto="palavra"),))

    def test_corridas_de_atributo_diferente_nao_se_fundem(self) -> None:
        fundidas = rico.fundir(
            [
                rico.Corrida(texto="uma "),
                rico.Corrida(texto="palavra", atributos=rico.Atributos(negrito=True)),
                rico.Corrida(texto=" só"),
            ]
        )
        self.assertEqual([c.texto for c in fundidas], ["uma ", "palavra", " só"])

    def test_corridas_de_blocos_diferentes_nao_se_fundem(self) -> None:
        """Mesmo texto e mesmos atributos: o que separa é a origem, e ela é o que a S-239 usa."""
        fundidas = rico.fundir(
            [rico.Corrida(texto="a", bloco=0), rico.Corrida(texto="b", bloco=1)]
        )
        self.assertEqual(len(fundidas), 2)

    def test_a_fusao_e_idempotente(self) -> None:
        uma_vez = rico.fundir([rico.Corrida(texto=letra) for letra in "abc"])
        self.assertEqual(rico.fundir(uma_vez), uma_vez)

    def test_a_fusao_preserva_o_texto(self) -> None:
        partido = [
            rico.Corrida(texto="ab"),
            rico.Corrida(texto="c", atributos=rico.Atributos(italico=True)),
            rico.Corrida(texto="de"),
            rico.Corrida(texto="f"),
        ]
        antes = "".join(c.texto for c in partido)
        self.assertEqual("".join(c.texto for c in rico.fundir(partido)), antes)

    def test_a_corrida_vazia_some(self) -> None:
        fundidas = rico.fundir([rico.Corrida(texto=""), rico.Corrida(texto="a")])
        self.assertEqual(fundidas, (rico.Corrida(texto="a"),))

    def test_normalizado_funde_e_mantem_a_origem(self) -> None:
        pagina = _pagina(_texto("a"))
        doc = rico.DocumentoRico(
            corridas=(rico.Corrida(texto="x"), rico.Corrida(texto="y")), origem=pagina
        )
        normalizado = doc.normalizado()
        self.assertEqual(normalizado.para_texto(), "xy")
        self.assertEqual(len(normalizado.corridas), 1)
        self.assertIs(normalizado.origem, pagina)


class SerializacaoTests(unittest.TestCase):
    def test_o_documento_serializa_e_volta_sem_perda(self) -> None:
        pagina = _pagina(
            _texto("prosa"),
            BlocoDeDiagrama(indice=0, bbox=(1.0, 2.0, 3.0, 4.0), confianca=0.8),
            _texto("lance", 0.5, "glifo"),
        )
        doc = rico.de_pagina(pagina)
        volta = rico.DocumentoRico.de_json(doc.para_json())
        self.assertEqual(volta.corridas, doc.corridas)
        self.assertEqual(volta.para_texto(), doc.para_texto())
        self.assertIsNotNone(volta.origem)
        self.assertEqual(volta.origem.para_json(), pagina.para_json())

    def test_o_documento_sem_pagina_serializa(self) -> None:
        doc = rico.de_texto("escrito do zero")
        volta = rico.DocumentoRico.de_json(doc.para_json())
        self.assertEqual(volta, doc)
        self.assertIsNone(volta.origem)

    def test_o_json_omite_o_que_e_padrao(self) -> None:
        """Um documento de prosa comum não carrega cinco chaves de atributo por trecho."""
        self.assertEqual(rico.Corrida(texto="a").para_json(), {"texto": "a"})
        self.assertEqual(rico.Atributos().para_json(), {})

    def test_o_atributo_nao_padrao_aparece_sozinho(self) -> None:
        self.assertEqual(rico.Atributos(negrito=True).para_json(), {"negrito": True})

    def test_atributo_de_versao_futura_e_ignorado(self) -> None:
        """Arquivo gravado por versão mais nova abre sem o atributo que esta não conhece."""
        voltou = rico.Atributos.de_json({"negrito": True, "riscado": True})
        self.assertEqual(voltou, rico.Atributos(negrito=True))

    def test_a_corrida_que_nao_e_objeto_levanta(self) -> None:
        with self.assertRaises(ValueError):
            rico.Corrida.de_json(["texto"])


class RecusaTests(unittest.TestCase):
    """Nome desconhecido levanta, em vez de virar o valor vazio -- a regra de `estilo_de_botao`."""

    def test_cor_fora_do_registro_levanta(self) -> None:
        with self.assertRaises(KeyError):
            rico.Atributos(cor="vermelho")

    def test_estilo_fora_do_registro_levanta(self) -> None:
        with self.assertRaises(KeyError):
            rico.Atributos(estilo="TITULO")

    def test_o_registro_de_cor_nasce_vazio(self) -> None:
        """A S-242 é quem o povoa; declarar nome que nada aplica é a promessa vazia da S-161."""
        self.assertEqual(rico.CORES_DE_AUTOR, ())
        self.assertEqual(rico.ESTILOS, ())

    def test_tipo_desconhecido_levanta(self) -> None:
        with self.assertRaises(KeyError):
            rico.Corrida(texto="a", tipo="tabela")

    def test_procedencia_desconhecida_levanta(self) -> None:
        with self.assertRaises(KeyError):
            rico.Corrida(texto="a", procedencia="chute")  # type: ignore[arg-type]

    def test_faixa_desconhecida_levanta(self) -> None:
        with self.assertRaises(KeyError):
            rico.Corrida(texto="a", faixa="talvez")

    def test_as_procedencias_saem_do_Literal(self) -> None:
        """Derivadas, e não recopiadas: a lista copiada é a que fica para trás."""
        self.assertEqual(set(rico.PROCEDENCIAS), {"camada", "glifo", "rapidocr", "humano"})


class FronteiraTests(unittest.TestCase):
    def test_o_modulo_nao_importa_tkinter(self) -> None:
        """A mesma varredura da S-145 sobre `ui/tokens.py`, e pelo mesmo motivo: o documento que
        sobrevive ao widget não pode depender do widget."""
        arvore = ast.parse(Path(rico.__file__).read_text(encoding="utf-8"))
        importados: set[str] = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                importados.update(alias.name.split(".")[0] for alias in no.names)
            elif isinstance(no, ast.ImportFrom) and no.module:
                importados.add(no.module.split(".")[0])
        self.assertNotIn("tkinter", importados)

    def test_o_modulo_nao_importa_a_interface(self) -> None:
        """`cor` é nome de domínio, e quem o resolve em tinta é a interface -- como `PAPEL_DA_FAIXA`."""
        texto = Path(rico.__file__).read_text(encoding="utf-8")
        self.assertNotIn("from ..ui", texto)
        self.assertNotIn("import ui", texto)


def _linhas(*pares: tuple[str, bool | None]) -> BlocoDeTexto:
    """Um bloco de várias linhas, cada uma com o seu pendor."""
    return BlocoDeTexto.de_linhas(
        [
            LinhaLida(txt, (0.0, 0.0, 10.0, 10.0), 1.0, "glifo", None, pendor)  # type: ignore[arg-type]
            for txt, pendor in pares
        ]
    )


class TipografiaMistaTests(unittest.TestCase):
    """O bloco só declara o que vale para **todas** as linhas -- e na página real isso é nada.

    Medida a folha 311 do `Secrets of Chess Training`: 19 linhas em itálico, uma citação de 17
    seguidas, e **nenhum bloco itálico** -- a citação e a prosa em volta caíram no mesmo parágrafo
    de 38 linhas. Desenhar por bloco ali seria desenhar nada, e é por isso que a ponte parte o
    bloco nas corridas que o desenham.
    """

    MISTO = (("prosa em pé", False), ("citação inclinada", True), ("prosa de novo", False))

    def test_um_bloco_de_tipografia_mista_vira_varias_corridas(self) -> None:
        doc = rico.de_pagina(_pagina(_linhas(*self.MISTO)))
        self.assertEqual([c.atributos.italico for c in doc.corridas], [False, True, False])

    def test_linhas_vizinhas_iguais_ficam_na_mesma_corrida(self) -> None:
        doc = rico.de_pagina(_pagina(_linhas(("uma", True), ("outra", True), ("terceira", True))))
        self.assertEqual(len(doc.corridas), 1)
        self.assertEqual(doc.corridas[0].texto, "uma outra terceira")

    def test_o_corte_por_linha_nao_muda_o_texto(self) -> None:
        """A trava da S-235 vale caractere a caractere, e é ela que o corte não pode quebrar."""
        pagina = _pagina(_linhas(*self.MISTO), _texto("outro bloco"))
        esperado = "".join(s.texto for s in documento.segmentos(pagina))
        self.assertEqual(rico.de_pagina(pagina).para_texto(), esperado)

    def test_o_espaco_da_juncao_fica_na_corrida_anterior(self) -> None:
        """Assim a corrida itálica começa na primeira letra, e não num espaço em pé antes dela."""
        doc = rico.de_pagina(_pagina(_linhas(*self.MISTO)))
        self.assertTrue(doc.corridas[0].texto.endswith(" "))
        self.assertTrue(doc.corridas[1].texto.startswith("citação"))
        self.assertFalse(doc.corridas[-1].texto.endswith(" "))

    def test_o_desconhecido_nao_parte_o_bloco(self) -> None:
        """`None` conta como "não", como na tela -- senão toda linha curta abriria uma corrida."""
        doc = rico.de_pagina(_pagina(_linhas(("em pé", False), ("curta", None))))
        self.assertEqual(len(doc.corridas), 1)

    def test_o_bloco_de_uma_linha_so_nao_e_partido(self) -> None:
        doc = rico.de_pagina(_pagina(_linhas(("única", True))))
        self.assertEqual([c.texto for c in doc.corridas], ["única"])
        self.assertTrue(doc.corridas[0].atributos.italico)

    def test_as_corridas_partidas_guardam_o_mesmo_bloco(self) -> None:
        """É o que mantém a S-239 intacta: a correção continua atada ao bloco que ela corrige."""
        doc = rico.de_pagina(_pagina(_linhas(*self.MISTO)))
        self.assertEqual({c.bloco for c in doc.corridas}, {0})
        self.assertEqual({c.procedencia for c in doc.corridas}, {"glifo"})

    def test_o_bloco_que_junta_de_outro_jeito_sai_inteiro(self) -> None:
        """A guarda: se a soma das linhas não bate com o texto do bloco, não se arrisca parti-lo.

        O texto vale mais que o atributo, e é ele que a S-235 travou."""
        diagrama = BlocoDeDiagrama(indice=0, bbox=(0.0, 0.0, 5.0, 5.0))
        doc = rico.de_pagina(_pagina(diagrama))
        self.assertEqual([c.texto for c in doc.corridas], ["[Diagrama 1]"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
