"""A régua de estilo desceu da linha ao caractere (S-429).

**O teste que carrega este arquivo é o do texto que não muda.** O corte fino parte a linha em mais
corridas, e a única coisa que ele não pode fazer é acrescentar ou comer um caractere: `de_pagina`
tem de continuar devolvendo, letra por letra, o mesmo texto que a `PaginaLida` tem. É a trava que a
S-235 pôs, e é ela que separa "desenhar melhor" de "reescrever a folha".

O segundo é o da **degradação**: onde a camada não sabe dizer -- folha sem camada, página girada,
texto que não casa --, o resultado tem de ser exatamente o de antes deste item existir. Um recurso
novo que piora o caso em que ele não se aplica não vale o que custa.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from chess_diagram_ocr.text import camada, rico
from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida

LINHA = (10.0, 100.0, 110.0, 112.0)


def de_camada(texto: str, *marcados: tuple[int, int], bbox: camada.Retangulo = LINHA) -> camada.LinhaDeCamada:
    """Uma linha de camada com os intervalos dados no estilo. O atalho dos testes daqui."""
    return camada.LinhaDeCamada(
        bbox=bbox,
        texto=texto,
        marcas=tuple(any(a <= i < b for a, b in marcados) for i in range(len(texto))),
    )


def lida(texto: str, **campos: object) -> LinhaLida:
    return LinhaLida(texto=texto, bbox=LINHA, confianca=1.0, procedencia="camada", **campos)  # type: ignore[arg-type]


def pagina(*linhas: LinhaLida) -> PaginaLida:
    bloco = BlocoDeTexto.de_linhas(list(linhas))
    return PaginaLida(documento="", pagina=0, colunas=(Coluna(indice=0, blocos=(bloco,)),))


class LinhasComTests(unittest.TestCase):
    """`linhas_com` lê o mesmo `get_text("dict")` de `spans_com`, e devolve um bool por caractere."""

    def _pagina(self, *spans: tuple[str, str]) -> object:
        class Falsa:
            def get_text(self, _formato: str) -> dict:
                return {
                    "blocks": [
                        {
                            "lines": [
                                {
                                    "bbox": LINHA,
                                    "spans": [
                                        {"text": texto, "font": fonte, "bbox": LINHA}
                                        for texto, fonte in spans
                                    ],
                                }
                            ]
                        }
                    ]
                }

        return Falsa()

    def test_a_marca_e_por_caractere_e_segue_o_span(self) -> None:
        from chess_diagram_ocr.text import negrito as ng

        [linha] = ng.linhas_de_negrito(self._pagina(("1.e4 ", "Times-Roman"), ("Nf3", "Times-Bold")))
        self.assertEqual(linha.texto, "1.e4 Nf3")
        self.assertEqual(linha.marcas, (False,) * 5 + (True,) * 3)

    def test_o_espaco_do_span_nao_e_normalizado(self) -> None:
        """Colapsar espaço aqui deslocaria toda marca depois dele. Quem tolera é o casamento."""
        [linha] = camada.linhas_com(self._pagina(("a  b", "X")), lambda _s: True)
        self.assertEqual(linha.texto, "a  b")
        self.assertEqual(len(linha.marcas), 4)

    def test_pagina_sem_camada_devolve_vazio(self) -> None:
        class Sem:
            def get_text(self, _formato: str) -> dict:
                raise RuntimeError("sem camada")

        self.assertEqual(camada.linhas_com(Sem(), lambda _s: True), [])


class TrechosTests(unittest.TestCase):
    """O casamento entre o que o motor leu e o que a camada declara."""

    def test_o_texto_identico_casa_exato(self) -> None:
        linha = de_camada("1.e4 e5 2.Nf3", (0, 4))
        self.assertEqual(camada.trechos(LINHA, "1.e4 e5 2.Nf3", [linha]), ((0, 4),))

    def test_o_espaco_entre_duas_palavras_marcadas_entra(self) -> None:
        """Um negrito que para no espaço e recomeça sairiam dois trechos onde a folha tem um."""
        linha = de_camada("um dois tres", (0, 7))
        self.assertEqual(camada.trechos(LINHA, "um dois tres", [linha]), ((0, 7),))

    def test_o_espaco_das_pontas_fica_de_fora(self) -> None:
        linha = de_camada("um dois tres", (2, 8))
        self.assertEqual(camada.trechos(LINHA, "um dois tres", [linha]), ((3, 7),))

    def test_a_palavra_nao_sai_partida_por_erro_de_leitura(self) -> None:
        """`study` lido `smdy` (S-186): sem a régua de palavra sairia `s` e `dy` com um `m` em pé."""
        linha = de_camada("a study of the ending", (2, 7))
        self.assertEqual(camada.trechos(LINHA, "a smdy of the ending", [linha]), ((2, 6),))

    def test_dois_trechos_separados_por_texto_em_pe(self) -> None:
        linha = de_camada("1.e4! e a resposta 1...c5!", (0, 5), (19, 26))
        self.assertEqual(
            camada.trechos(LINHA, "1.e4! e a resposta 1...c5!", [linha]), ((0, 5), (19, 26))
        )

    def test_duas_linhas_de_camada_na_mesma_banda_sao_costuradas(self) -> None:
        """A linha lida pode ser a costura de duas da camada, e a ordem é por `x`."""
        esquerda = de_camada("esquerda", (0, 8), bbox=(0.0, 100.0, 40.0, 112.0))
        direita = de_camada("direita", bbox=(60.0, 100.0, 100.0, 112.0))
        self.assertEqual(
            camada.trechos((0.0, 100.0, 100.0, 112.0), "esquerda direita", [direita, esquerda]),
            ((0, 8),),
        )


class DegradacaoTests(unittest.TestCase):
    """Onde a camada não sabe dizer, o resultado é vazio -- e vazio devolve o comportamento antigo."""

    def test_sem_linha_de_camada_nenhuma_e_vazio(self) -> None:
        self.assertEqual(camada.trechos(LINHA, "qualquer coisa", []), ())

    def test_a_linha_que_nao_se_sobrepoe_nao_conta(self) -> None:
        """A página girada cai aqui: `spans_com` também não gira, e as caixas ficam em sistemas
        diferentes. Vazio, e a régua de maioria continua respondendo."""
        longe = de_camada("1.e4 e5", (0, 4), bbox=(10.0, 500.0, 110.0, 512.0))
        self.assertEqual(camada.trechos(LINHA, "1.e4 e5", [longe]), ())

    def test_o_texto_que_discorda_demais_e_recusado(self) -> None:
        """Camada que é palpite de outro OCR: `difflib` acha coincidência curta em qualquer par."""
        outra = de_camada("completamente outro texto aqui", (0, 12))
        self.assertEqual(camada.trechos(LINHA, "1.e4 e5 2.Nf3 Nc6", [outra]), ())

    def test_nada_marcado_e_vazio(self) -> None:
        self.assertEqual(camada.trechos(LINHA, "nada aqui", [de_camada("nada aqui")]), ())

    def test_texto_vazio_nao_estoura(self) -> None:
        self.assertEqual(camada.trechos(LINHA, "", [de_camada("x", (0, 1))]), ())


class RemapearTests(unittest.TestCase):
    """Os intervalos seguem o texto quando ele é reescrito depois de eles serem achados."""

    def test_a_juncao_de_hifen_desloca_o_que_vem_depois(self) -> None:
        antigo, novo = "em- barrassment e o fim", "embarrassment e o fim"
        [trecho] = camada.remapear(((16, 23),), antigo, novo)
        self.assertEqual(novo[trecho[0] : trecho[1]], antigo[16:23])

    def test_o_texto_igual_devolve_os_mesmos(self) -> None:
        self.assertEqual(camada.remapear(((0, 4),), "1.e4", "1.e4"), ((0, 4),))

    def test_sem_intervalo_nao_faz_nada(self) -> None:
        self.assertEqual(camada.remapear((), "a", "b"), ())

    def test_o_que_a_reescrita_comeu_nao_vira_intervalo(self) -> None:
        """Caractere que sumiu não tem estilo, e apontar para o vizinho seria pintar outra palavra."""
        self.assertEqual(camada.remapear(((0, 6),), "sumiu resto", "resto"), ())


class CorteDoDocumentoTests(unittest.TestCase):
    """O que o corte fino muda no desenho -- e o que ele não pode mudar."""

    def test_o_texto_da_pagina_nao_muda_um_caractere(self) -> None:
        pag = pagina(
            lida("23 b4 24 cxb4", negrito=True, negrito_em=((3, 5), (9, 13)), italico_em=((0, 2), (6, 8))),
            lida("e a resposta"),
        )
        self.assertEqual(rico.de_pagina(pag).para_texto(), pag.texto(com_marcas=True))

    def test_o_lance_no_meio_da_prosa_vira_corrida_propria(self) -> None:
        """O caso que a régua de maioria perdia: menos de 60% da linha, e a linha saía normal."""
        pag = pagina(lida("Em 24 axb4 mantém", negrito=False, negrito_em=((3, 10),)))
        negrito = [c.texto for c in rico.de_pagina(pag).corridas if c.atributos.negrito]
        self.assertEqual(negrito, ["24 axb4"])

    def test_o_que_a_maioria_inchava_volta_ao_tamanho(self) -> None:
        """A linha era 60% negrito e saía inteira em negrito: as palavras em pé do fim voltam."""
        pag = pagina(lida("1.e4 e5 2.Nf3 e a prosa", negrito=True, negrito_em=((0, 13),)))
        corridas = [(c.texto, c.atributos.negrito) for c in rico.de_pagina(pag).corridas]
        self.assertEqual(corridas, [("1.e4 e5 2.Nf3", True), (" e a prosa", False)])

    def test_sem_intervalo_a_linha_inteira_decide_como_antes(self) -> None:
        """A trava da degradação: uma folha sem camada tem de sair idêntica ao que saía."""
        pag = pagina(lida("uma linha", negrito=True), lida("outra linha", negrito=True))
        corridas = rico.de_pagina(pag).corridas
        self.assertEqual([c.texto for c in corridas], ["uma linha outra linha"])
        self.assertTrue(corridas[0].atributos.negrito)

    def test_o_espaco_da_juncao_fica_no_fim_da_corrida_anterior(self) -> None:
        """A corrida em negrito começa na primeira letra dele, e não num espaço em pé antes."""
        pag = pagina(lida("prosa"), lida("1.e4", negrito=True, negrito_em=((0, 4),)))
        corridas = rico.de_pagina(pag).corridas
        self.assertEqual([(c.texto, c.atributos.negrito) for c in corridas], [("prosa ", False), ("1.e4", True)])

    def test_o_peso_e_o_pendor_cortam_juntos(self) -> None:
        """O número do lance em itálico e o lance em negrito são duas corridas, e não uma."""
        pag = pagina(lida("24 cxb4", negrito_em=((3, 7),), italico_em=((0, 2),)))
        corridas = [
            (c.texto, c.atributos.negrito, c.atributos.italico) for c in rico.de_pagina(pag).corridas
        ]
        self.assertEqual(corridas, [("24", False, True), (" ", False, False), ("cxb4", True, False)])


class ArquivoTests(unittest.TestCase):
    """Os intervalos sobrevivem à ida e à volta do `.json`, e o arquivo antigo continua legível."""

    def test_a_ida_e_a_volta_preservam_os_intervalos(self) -> None:
        linha = lida("24 cxb4", negrito_em=((3, 7),), italico_em=((0, 2),))
        volta = LinhaLida.de_json(linha.para_json())
        self.assertEqual(volta.negrito_em, ((3, 7),))
        self.assertEqual(volta.italico_em, ((0, 2),))

    def test_o_arquivo_antigo_sem_o_campo_vira_vazio(self) -> None:
        """Gravado antes da S-429: não tem o campo, e não é inválido por isso."""
        dados = lida("24 cxb4").para_json()
        del dados["negrito_em"]
        del dados["italico_em"]
        self.assertEqual(LinhaLida.de_json(dados).negrito_em, ())

    def test_o_par_fora_de_ordem_recusa(self) -> None:
        """Ele atravessaria `rico` sem erro e sumiria na tela, que é o defeito mais caro de achar."""
        from chess_diagram_ocr.text.pagina import PaginaInvalida

        dados = lida("24 cxb4").para_json() | {"negrito_em": [[7, 3]]}
        with self.assertRaises(PaginaInvalida):
            LinhaLida.de_json(dados)

    def test_o_campo_que_nao_e_lista_recusa(self) -> None:
        from chess_diagram_ocr.text.pagina import PaginaInvalida

        dados = lida("24 cxb4").para_json() | {"italico_em": "negrito"}
        with self.assertRaises(PaginaInvalida):
            LinhaLida.de_json(dados)


class DaFolhaAoDocumentoTests(unittest.TestCase):
    """O caminho inteiro, com um PDF de verdade: span em negrito -> corrida em negrito na aba."""

    def _livro(self, pasta: Path) -> Path:
        """Uma folha com uma linha em que **só uma palavra** tem peso -- o caso que sumia.

        `helv` e `hebo` são a Helvetica normal e a Bold que o PyMuPDF traz de fábrica: o nome da
        fonte que chega ao `get_text("dict")` é `Helvetica-Bold`, que é o que `FONTE_NEGRITO` lê.
        """
        import fitz

        caminho = pasta / "livro.pdf"
        doc = fitz.open()
        folha = doc.new_page(width=400.0, height=200.0)
        folha.insert_text((40.0, 60.0), "Em ", fontsize=11, fontname="helv")
        folha.insert_text((60.0, 60.0), "24 axb4", fontsize=11, fontname="hebo")
        # Colado ao anterior de propósito: com um vão de 10 pt o PyMuPDF abre **outra** linha, e o
        # caso que interessa -- uma palavra em negrito no meio de uma linha em pé -- não aconteceria.
        folha.insert_text((100.5, 60.0), " mantem a iniciativa", fontsize=11, fontname="helv")
        doc.save(str(caminho))
        doc.close()
        return caminho

    def test_a_palavra_em_negrito_chega_como_corrida_propria(self) -> None:
        from tempfile import TemporaryDirectory

        from chess_diagram_ocr.text import leitor

        with TemporaryDirectory() as pasta:
            pag = leitor.ler_pagina(self._livro(Path(pasta)), 0, dpi=110, motor="camada")

        linhas = [linha for bloco in pag.blocos for linha in getattr(bloco, "linhas", ())]
        self.assertTrue(linhas, "a folha tem uma linha de texto")
        [linha] = linhas
        inicio, fim = linha.negrito_em[0]
        self.assertEqual(linha.texto[inicio:fim], "24 axb4")

        negrito = [c.texto for c in rico.de_pagina(pag).corridas if c.atributos.negrito]
        self.assertEqual(negrito, ["24 axb4"])

    def test_a_regua_de_linha_sozinha_teria_perdido_a_palavra(self) -> None:
        """O contrafactual, e é ele que diz que este item entrega alguma coisa: `24 axb4` cobre
        menos de 60% da largura, e o campo de linha continua dizendo -- corretamente -- que a
        linha não é uma linha de negrito."""
        from tempfile import TemporaryDirectory

        from chess_diagram_ocr.text import leitor

        with TemporaryDirectory() as pasta:
            pag = leitor.ler_pagina(self._livro(Path(pasta)), 0, dpi=110, motor="camada")

        [linha] = [linha for bloco in pag.blocos for linha in getattr(bloco, "linhas", ())]
        self.assertFalse(linha.negrito)
        self.assertTrue(linha.negrito_em)


class HifenRemapeadoTests(unittest.TestCase):
    """A junção da palavra partida acontece **depois** do casamento, e os intervalos a acompanham."""

    LEXICO = frozenset({"development", "for", "white", "nice"})

    def _cru(self, texto: str, y1: int, y2: int, **campos: object):  # noqa: ANN202 - leitor._Cru
        from chess_diagram_ocr.text import leitor
        from chess_diagram_ocr.text.boxes import Caixa

        return leitor._Cru(
            texto=texto, caixa=Caixa(20, y1, 240, y2), confianca=1.0, procedencia="camada", **campos  # type: ignore[arg-type]
        )

    def test_o_negrito_do_fim_da_linha_juntada_continua_na_palavra_certa(self) -> None:
        from chess_diagram_ocr.text import leitor

        # `nice` em negrito, e `devel-` no fim: juntar traz `opment` da linha de baixo, e tudo o
        # que vem depois de `nice` anda. Sem remapear, o intervalo apontaria para outra palavra.
        cruas = [
            self._cru("a nice devel-", 20, 34, negrito_em=((2, 6),)),
            self._cru("opment for white", 36, 50),
        ]
        colunas = leitor.montar(cruas, (), escala_px=1.0, lexico=self.LEXICO)
        [linha, _] = [linha for c in colunas for b in c.blocos for linha in b.linhas]

        self.assertEqual(linha.texto, "a nice development")
        inicio, fim = linha.negrito_em[0]
        self.assertEqual(linha.texto[inicio:fim], "nice")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
