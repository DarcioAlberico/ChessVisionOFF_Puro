"""Estilo de parágrafo: título, prosa, notação e legenda (S-249).

**A página chega ao editor já sabendo o que é título e o que é prosa**, e até aqui o editor pintava
tudo igual: o modelo da S-211 distingue `BlocoDeTarja` de `BlocoDeTexto` e o `recuado` da S-199
separa parágrafo de continuação. O que estes testes travam é que a derivação use o que a página diz
-- e que os dois estilos **sem** dono medido continuem entrando só pela mão, que é a regra 5 da
SPEC_EDITOR.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from chess_diagram_ocr.text import documento, rico
from chess_diagram_ocr.text.pagina import (
    BlocoDeDiagrama,
    BlocoDeTarja,
    BlocoDeTexto,
    Coluna,
    LinhaLida,
    PaginaLida,
)

PAINEL = Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr" / "ui" / "texto_panel.py"


def _linha(texto: str, topo: float = 0.0) -> LinhaLida:
    return LinhaLida(texto, (0.0, topo, 100.0, topo + 9.0), 1.0, "camada")


def _pagina(*blocos: object) -> PaginaLida:
    return PaginaLida(
        documento="livro.pdf",
        pagina=0,
        colunas=(Coluna(indice=0, blocos=tuple(blocos)),),  # type: ignore[arg-type]
    )


class ConjuntoFechadoTests(unittest.TestCase):
    def test_o_conjunto_de_estilos_e_fechado(self) -> None:
        """Como `GRUPOS` em `ui/comandos.py`: quatro, e nenhum quinto entra por engano."""
        self.assertEqual(rico.ESTILOS, ("titulo", "prosa", "notacao", "legenda"))

    def test_estilo_desconhecido_levanta(self) -> None:
        with self.assertRaises(KeyError):
            rico.Atributos(estilo="epigrafe")
        with self.assertRaises(KeyError):
            rico.aplicar_estilo(rico.de_texto("texto"), 0, 5, "epigrafe")


class DerivadoDaPaginaTests(unittest.TestCase):
    def test_a_tarja_vira_titulo(self) -> None:
        """Texto claro sobre fundo escuro é cabeçalho (S-195), e a página já o distingue."""
        doc = rico.de_pagina(_pagina(BlocoDeTarja(linhas=(_linha("CAPÍTULO 3"),))))
        self.assertEqual({c.atributos.estilo for c in doc.corridas if c.texto.strip()}, {"titulo"})

    def test_o_recuo_vira_prosa(self) -> None:
        recuado = BlocoDeTexto.de_linhas([_linha("O parágrafo começa recuado.")], recuado=True)
        continuacao = BlocoDeTexto.de_linhas([_linha("Esta linha não.", 20.0)])
        doc = rico.de_pagina(_pagina(recuado, continuacao))
        estilos = {c.texto.strip()[:9]: c.atributos.estilo for c in doc.corridas if c.texto.strip()}
        self.assertEqual(estilos["O parágra"], "prosa")
        self.assertEqual(estilos["Esta linh"], "")

    def test_a_marca_do_diagrama_nao_ganha_estilo(self) -> None:
        doc = rico.de_pagina(_pagina(BlocoDeDiagrama(indice=0, bbox=(0.0, 0.0, 9.0, 9.0))))
        self.assertEqual({c.atributos.estilo for c in doc.corridas}, {""})

    def test_a_legenda_segue_o_diagrama(self) -> None:
        """**O vínculo vem da página** (S-249): `BlocoDeTexto.legenda_de`, gravado pelo leitor a
        partir de `pdf_text.assign_lines_to_diagrams` -- a régua da S-16, e não uma regra nova."""
        from dataclasses import replace

        legenda = replace(
            BlocoDeTexto.de_linhas([_linha("Daugavpils 1986", 12.0)]), legenda_de=0
        )
        doc = rico.de_pagina(_pagina(BlocoDeDiagrama(indice=0, bbox=(0.0, 0.0, 9.0, 9.0)), legenda))
        estilos = {c.texto.strip(): c.atributos.estilo for c in doc.corridas if c.texto.strip()}
        self.assertEqual(estilos["Daugavpils 1986"], "legenda")

    def test_a_linha_de_lances_atada_ao_diagrama_nao_vira_legenda(self) -> None:
        """A guarda de conteúdo da S-249, com número: **15 dos 83** parágrafos que a régua ata a um
        diagrama no conjunto de campo são linha de lances, e pintá-los com o corpo de legenda seria
        um erro visível. Quem separa é `notacao.e_linha_de_notacao`."""
        from dataclasses import replace

        variante = replace(
            BlocoDeTexto.de_linhas([_linha("1...♖a8+! 2.♔b5 g3 3.♔c6", 12.0)]), legenda_de=0
        )
        doc = rico.de_pagina(_pagina(BlocoDeDiagrama(indice=0, bbox=(0.0, 0.0, 9.0, 9.0)), variante))
        self.assertEqual({c.atributos.estilo for c in doc.corridas}, {""})

    def test_a_legenda_ganha_do_recuo(self) -> None:
        """Um parágrafo pode ser as duas coisas, e o que ele **é** para quem lê é a legenda."""
        from dataclasses import replace

        legenda = replace(
            BlocoDeTexto.de_linhas([_linha("Bratislava 1956", 12.0)], recuado=True), legenda_de=1
        )
        doc = rico.de_pagina(_pagina(BlocoDeDiagrama(indice=1, bbox=(0.0, 0.0, 9.0, 9.0)), legenda))
        # Só as corridas de texto: a marca do diagrama não recebe estilo, por construção.
        estilos = {
            c.atributos.estilo for c in doc.corridas if c.tipo == rico.TEXTO and c.texto.strip()
        }
        self.assertEqual(estilos, {"legenda"})

    def test_notacao_nao_entra_sozinha(self) -> None:
        """**O único que continua entrando só pela mão**, e agora por medição (regra 5).

        Medido em 2026-08-26 sobre 305 blocos rotulados à mão
        (`docs/metrics/texto_notacao_estilo.json`): a régua acerta 89% do que estilaria e alcança
        75% das linhas de lances, e os 11% que erra são título corrente e número de página. Não
        chega para pintar sozinha. A guarda da legenda não é a mesma pergunta: ela decide sobre um
        parágrafo que já se sabe atado a um diagrama, e ali errar tira um estilo em vez de pôr um
        errado.
        """
        doc = rico.de_pagina(_pagina(BlocoDeTexto.de_linhas([_linha("1.♘f3 ♘f6 2.c4 e6")])))
        self.assertEqual({c.atributos.estilo for c in doc.corridas}, {""})

    def test_o_motivo_de_cada_um_esta_escrito_no_modulo(self) -> None:
        """A regra 5 exige que a decisão **se declare** no módulo, medida ou não.

        A frase mudou quando a medição chegou -- de *"não foi medida"* para o número que ela deu --,
        e é isso que este teste segue: o que ele exige é que o módulo diga de onde vem a decisão,
        e não que ele repita uma frase.
        """
        fonte = Path(rico.__file__).read_text(encoding="utf-8")
        self.assertIn("assign_lines_to_diagrams", fonte)
        self.assertIn("texto_notacao_estilo.json", fonte)
        self.assertIn("continua entrando só pela mão", fonte)


class AplicarAMaoTests(unittest.TestCase):
    def test_aplicar_a_mao_sobrepoe_e_carimba_humano(self) -> None:
        doc = rico.de_pagina(_pagina(BlocoDeTarja(linhas=(_linha("CAPÍTULO 3"),))))
        depois = rico.aplicar_estilo(doc, 0, 4, "notacao")
        marcadas = [c for c in depois.corridas if c.texto.strip()]
        self.assertEqual({c.atributos.estilo for c in marcadas}, {"notacao"})
        self.assertEqual({c.procedencia for c in marcadas}, {"humano"})

    def test_o_estilo_alcanca_o_paragrafo_e_para_nele(self) -> None:
        primeiro = BlocoDeTexto.de_linhas([_linha("Primeiro parágrafo inteiro.")], recuado=True)
        segundo = BlocoDeTexto.de_linhas([_linha("Segundo parágrafo.", 20.0)], recuado=True)
        doc = rico.de_pagina(_pagina(primeiro, segundo))
        depois = rico.aplicar_estilo(doc, 0, 3, "titulo")
        por_texto = {c.texto.strip()[:8]: c.atributos.estilo for c in depois.corridas if c.texto.strip()}
        self.assertEqual(por_texto["Primeiro"], "titulo")
        self.assertEqual(por_texto["Segundo "], "prosa")

    def test_o_estilo_sobrevive_ao_arquivo(self) -> None:
        """Ele é atributo do documento, e o `.cvtxt` guarda o que difere do padrão (S-238)."""
        from chess_diagram_ocr.text import arquivo

        doc = rico.aplicar_estilo(rico.de_texto("um título"), 0, 9, "titulo")
        de_volta = arquivo.de_json(arquivo.para_json(doc))
        self.assertEqual([c.atributos.estilo for c in de_volta.corridas], ["titulo"])


class SemTamanhoCravadoTests(unittest.TestCase):
    def test_nenhum_tamanho_de_fonte_cravado(self) -> None:
        """Critério de aceite: tudo passa por `ui/tipografia.py`.

        A varredura procura `font=(...)` com número literal e `size=` numérico no painel -- que é
        como um tamanho entraria. `tipografia` escala pela fonte do sistema desde a S-147, e cravar
        `12` aqui quebraria quem aumentou a fonte do Windows.
        """
        arvore = ast.parse(PAINEL.read_text(encoding="utf-8"))
        cravados: list[str] = []
        for no in ast.walk(arvore):
            if isinstance(no, ast.Call):
                for chave in no.keywords:
                    if chave.arg in ("size", "font") and isinstance(chave.value, ast.Constant):
                        if isinstance(chave.value.value, int):
                            cravados.append(f"linha {no.lineno}: {chave.arg}={chave.value.value}")
        self.assertEqual(cravados, [])

    def test_todo_estilo_tem_papel_de_tipografia(self) -> None:
        from chess_diagram_ocr.ui import texto_panel, tipografia

        self.assertEqual(set(texto_panel.PAPEL_DO_ESTILO), set(rico.ESTILOS))
        for papel in texto_panel.PAPEL_DO_ESTILO.values():
            with self.subTest(papel=papel):
                self.assertIn(papel, tipografia.PAPEIS_DE_FONTE)


class DocumentoIntactoTests(unittest.TestCase):
    def test_o_estilo_nao_muda_um_caractere(self) -> None:
        doc = rico.de_pagina(_pagina(BlocoDeTexto.de_linhas([_linha("texto qualquer")], recuado=True)))
        for estilo in rico.ESTILOS:
            with self.subTest(estilo=estilo):
                self.assertEqual(rico.aplicar_estilo(doc, 0, 5, estilo).para_texto(), doc.para_texto())

    def test_o_separador_nao_recebe_estilo(self) -> None:
        """Ele é estrutura que o leitor produziu, e ninguém o escreveu (S-235)."""
        doc = rico.de_pagina(
            _pagina(
                BlocoDeTexto.de_linhas([_linha("primeiro")], recuado=True),
                BlocoDeTexto.de_linhas([_linha("segundo", 20.0)], recuado=True),
            )
        )
        separadores = [c for c in doc.corridas if c.tipo == rico.SEPARADOR]
        self.assertTrue(separadores)
        self.assertEqual({c.atributos.estilo for c in separadores}, {""})
        self.assertEqual({c.faixa for c in separadores}, {documento.TRANQUILO})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
