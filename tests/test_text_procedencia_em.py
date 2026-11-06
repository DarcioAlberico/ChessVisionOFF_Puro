"""De quem é cada palavra, e o quanto ela vale: a procedência `tesseract` e os campos por intervalo (S-722).

**O formato novo só é gravado depois do portão G102**, e por isso metade destes testes afirma o que sai com a
constante desligada: nada que um programa anterior recuse. A outra metade liga a constante e cobra a ida e volta.
"""

from __future__ import annotations

import json
import unittest
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, get_args
from unittest import mock

from ambiente_de_teste import pasta_temporaria
from test_text_fiacao_da_prosa import ESCALA, LINHA, _ComLivro, _crua, _Falso, _linhas

from chess_diagram_ocr.text import (
    arquivo,
    caderno,
    camada_prosa,
    correcao,
    dado_corrigido,
    documento,
    exportacao,
    leitor,
    pagina,
    rico,
    tesseract,
)
from chess_diagram_ocr.text.pagina import (
    ORDEM_DE_CONFIANCA,
    PROCEDENCIAS,
    BlocoDeTexto,
    Coluna,
    LinhaLida,
    PaginaInvalida,
    PaginaLida,
    Procedencia,
    menos_confiavel,
)

CAIXA = (10.0, 10.0, 200.0, 22.0)
ANTIGAS = {"camada", "glifo", "rapidocr", "humano"}
"""O que um programa anterior à S-722 aceita. Fora disto, ele levanta `PaginaInvalida` e não abre o arquivo."""


def _mista(texto: str = "the wbite wins") -> LinhaLida:
    """`the` e `wins` do Tesseract, `wbite` do glifo. A linha leva a menos confiável das que a compõem."""
    return LinhaLida(
        texto=texto,
        bbox=CAIXA,
        confianca=0.9,
        procedencia="glifo",
        procedencia_em=((0, 3, "tesseract"), (4, 9, "glifo"), (10, 14, "tesseract")),
        confianca_em=((0, 3, 0.97), (4, 9, 0.20), (10, 14, 0.91)),
    )


def _pagina_com(*linhas: LinhaLida, **campos: Any) -> PaginaLida:
    bloco = BlocoDeTexto.de_linhas(list(linhas))
    return PaginaLida(pagina=3, largura=400.0, altura=600.0, documento="livro.pdf", colunas=(Coluna(blocos=(bloco,)),), **campos)


def _procedencias_no(dados: Any) -> set[str]:
    """Toda `procedencia` escrita em qualquer nível do JSON: é o que um programa anterior vai cobrar."""
    achadas: set[str] = set()
    if isinstance(dados, dict):
        for chave, valor in dados.items():
            if chave == "procedencia" and isinstance(valor, str):
                achadas.add(valor)
            achadas |= _procedencias_no(valor)
    elif isinstance(dados, list):
        for item in dados:
            achadas |= _procedencias_no(item)
    return achadas


class FormatoNovoLigado(unittest.TestCase):
    """A ida e volta, com o interruptor que o G102 vai virar."""

    def setUp(self) -> None:
        ligado = mock.patch.object(pagina, "GRAVAR_FORMATO_NOVO", True)
        ligado.start()
        self.addCleanup(ligado.stop)


class AProcedenciaTests(unittest.TestCase):
    def test_o_literal_as_duas_tuplas_e_o_rico_dizem_o_mesmo(self) -> None:
        self.assertEqual(set(get_args(Procedencia)), set(PROCEDENCIAS))
        self.assertEqual(set(PROCEDENCIAS), set(ORDEM_DE_CONFIANCA))
        self.assertEqual(set(rico.PROCEDENCIAS), set(PROCEDENCIAS))
        self.assertIn("tesseract", PROCEDENCIAS)

    def test_a_posicao_do_tesseract_e_declarada(self) -> None:
        """Acima do glifo na prosa medida, abaixo do que não é leitura. `rapidocr` não lê acento, e fica embaixo."""
        self.assertEqual(ORDEM_DE_CONFIANCA, ("rapidocr", "glifo", "tesseract", "camada", "humano"))

    def test_menos_confiavel_com_tesseract_nao_levanta(self) -> None:
        self.assertEqual(menos_confiavel(["tesseract", "camada"]), "tesseract")
        self.assertEqual(menos_confiavel(["tesseract", "glifo"]), "glifo")
        self.assertEqual(menos_confiavel(["tesseract", "rapidocr"]), "rapidocr")
        self.assertEqual(menos_confiavel(["humano", "tesseract"]), "tesseract")

    def test_a_procedencia_de_cada_posicao(self) -> None:
        linha = _mista()
        self.assertEqual(linha.procedencia_no(0), "tesseract")
        self.assertEqual(linha.procedencia_no(5), "glifo")
        self.assertEqual(linha.procedencia_no(13), "tesseract")
        # Sem detalhe, vale o campo da linha: é o contrato de `negrito_em`.
        self.assertEqual(LinhaLida("abc", CAIXA, procedencia="camada").procedencia_no(1), "camada")

    def test_a_palavra_do_bloco_diz_de_quem_e(self) -> None:
        bloco = BlocoDeTexto.de_linhas([_mista(), LinhaLida("black loses", CAIXA, procedencia="tesseract")])
        self.assertEqual(
            [bloco.procedencia_da_palavra(n) for n in range(5)], ["tesseract", "glifo", "tesseract", "tesseract", "tesseract"]
        )
        self.assertEqual(bloco.procedencia, "glifo", "o bloco continua valendo o pior pedaço dele")


class ComAConstanteDesligadaTests(unittest.TestCase):
    """O padrão, até o G102: **um programa anterior abre o que este grava**."""

    def test_a_constante_nasce_desligada(self) -> None:
        self.assertFalse(pagina.GRAVAR_FORMATO_NOVO, "o formato novo só é gravado depois do portão G102")

    def test_a_pagina_sai_no_formato_de_antes(self) -> None:
        dados = _pagina_com(_mista(), LinhaLida("black loses", CAIXA, procedencia="tesseract")).para_json()
        self.assertEqual(dados["esquema"], 1)
        self.assertLessEqual(_procedencias_no(dados), ANTIGAS)
        linhas = dados["colunas"][0]["blocos"][0]["linhas"]
        self.assertNotIn("procedencia_em", linhas[0])
        self.assertNotIn("confianca_em", linhas[0])
        self.assertEqual(linhas[1]["procedencia"], "glifo", "o `tesseract` sai como a leitura saía antes da S-722")

    def test_o_aviso_continua_pagando_so_o_esquema_dele(self) -> None:
        dados = _pagina_com(_mista(), avisos=(pagina.Aviso(pagina.FOLHA_NAO_LIDA, "x"),)).para_json()
        self.assertEqual(dados["esquema"], 2)

    def test_o_arquivo_inteiro_sai_na_versao_de_antes(self) -> None:
        doc = rico.de_pagina(_pagina_com(_mista()))
        self.assertIn("tesseract", {c.procedencia for c in doc.corridas})
        dados = arquivo.para_json(doc)
        self.assertEqual(dados["versao"], arquivo.VERSAO_DE_ANTES)
        self.assertEqual(dados["versao"], 1)
        self.assertLessEqual(_procedencias_no(dados), ANTIGAS)

    def test_a_tela_continua_lendo_os_campos_em_memoria(self) -> None:
        """A constante é do arquivo. O que a leitura produziu continua inteiro até ser gravado."""
        self.assertEqual(_pagina_com(_mista()).blocos[0].linhas[0].procedencia_em[0], (0, 3, "tesseract"))


class FormatoAntigoTests(unittest.TestCase):
    ANTIGO = {  # noqa: RUF012
        "versao": 1,
        "documento": {
            "corridas": [{"texto": "Nf3 wins", "bloco": 0, "procedencia": "glifo"}],
            "origem": {
                "esquema": 1,
                "documento": "livro.pdf",
                "pagina": 2,
                "largura": 100.0,
                "altura": 200.0,
                "unidade": "pt",
                "numero_impresso": None,
                "cabecalho": None,
                "rodape": None,
                "colunas": [
                    {
                        "indice": 0,
                        "bbox": [0, 0, 1, 1],
                        "blocos": [
                            {
                                "tipo": "texto",
                                "bbox": [0, 0, 1, 1],
                                "confianca": 0.8,
                                "procedencia": "glifo",
                                "linhas": [{"texto": "Nf3 wins", "bbox": [0, 0, 1, 1], "confianca": 0.8, "procedencia": "glifo"}],
                            }
                        ],
                    }
                ],
            },
        },
    }

    def test_o_arquivo_de_antes_abre_igual(self) -> None:
        doc = arquivo.de_json(json.loads(json.dumps(self.ANTIGO)))
        assert doc.origem is not None
        linha = doc.origem.blocos[0].linhas[0]
        self.assertEqual(doc.para_texto(), "Nf3 wins")
        self.assertEqual(linha.procedencia, "glifo")
        self.assertEqual(linha.procedencia_em, ())
        self.assertEqual(linha.confianca_em, ())
        self.assertEqual(linha.procedencia_no(2), "glifo")

    def test_o_arquivo_de_antes_regravado_nao_muda(self) -> None:
        doc = arquivo.de_json(json.loads(json.dumps(self.ANTIGO)))
        self.assertEqual(arquivo.para_json(doc)["versao"], 1)
        self.assertEqual(arquivo.para_json(doc)["documento"]["origem"]["esquema"], 1)

    def test_a_versao_futura_continua_recusada(self) -> None:
        dados = json.loads(json.dumps(self.ANTIGO))
        dados["versao"] = arquivo.VERSAO + 1
        with self.assertRaises(arquivo.VersaoFutura):
            arquivo.de_json(dados)
        dados["versao"] = 1
        dados["documento"]["origem"]["esquema"] = pagina.ESQUEMA + 1
        with self.assertRaises(PaginaInvalida):
            arquivo.de_json(dados)


class IdaEVoltaTests(FormatoNovoLigado):
    def test_o_formato_novo_paga_versao_e_esquema(self) -> None:
        doc = rico.de_pagina(_pagina_com(_mista()))
        dados = arquivo.para_json(doc)
        self.assertEqual(dados["versao"], arquivo.VERSAO)
        self.assertEqual(dados["versao"], 2)
        self.assertEqual(dados["documento"]["origem"]["esquema"], pagina.ESQUEMA)
        self.assertEqual(pagina.ESQUEMA, 3)

    def test_a_folha_sem_nada_novo_continua_no_formato_de_antes(self) -> None:
        """A regra da S-710: só paga quem precisa, e um programa anterior continua abrindo o resto."""
        doc = rico.de_pagina(_pagina_com(LinhaLida("abc", CAIXA, confianca=0.9, procedencia="glifo")))
        dados = arquivo.para_json(doc)
        self.assertEqual(dados["versao"], 1)
        self.assertEqual(dados["documento"]["origem"]["esquema"], 1)
        self.assertNotIn("procedencia_em", dados["documento"]["origem"]["colunas"][0]["blocos"][0]["linhas"][0])

    def test_a_pagina_volta_sem_perda(self) -> None:
        original = _pagina_com(_mista(), LinhaLida("black loses", CAIXA, procedencia="tesseract"))
        volta = PaginaLida.de_json(json.loads(json.dumps(original.para_json())))
        self.assertEqual(volta, original)
        self.assertEqual(volta.para_json(), original.para_json())

    def test_o_cvtxt_volta_sem_perda(self) -> None:
        doc = rico.de_pagina(_pagina_com(_mista()))
        caminho = arquivo.gravar(pasta_temporaria(self) / "a.cvtxt", doc)
        volta = arquivo.carregar(caminho)
        self.assertEqual(volta.origem, doc.origem)
        self.assertEqual(volta.corridas, doc.corridas)

    def test_o_caderno_volta_sem_perda(self) -> None:
        pasta = pasta_temporaria(self)
        livro_pdf = pasta / "livro.pdf"
        livro_pdf.write_bytes(b"%PDF-1.7\n" + bytes(range(256)) * 64)
        doc = rico.de_pagina(replace(_pagina_com(_mista()), documento=str(livro_pdf)))
        livro = caderno.abrir(livro_pdf, pasta=pasta / "cadernos")
        assert livro is not None
        self.addCleanup(livro.fechar)
        livro.gravar(doc, motor="fusao:eng")
        volta = livro.folha(3)
        assert volta is not None
        self.assertEqual(volta.origem, doc.origem)
        self.assertEqual(volta.corridas, doc.corridas)


class ArquivoEstragadoTests(unittest.TestCase):
    def _linha(self, **campos: Any) -> dict[str, Any]:
        return {"texto": "abc", "bbox": list(CAIXA), "procedencia": "glifo", **campos}

    def test_procedencia_de_intervalo_que_nao_existe_levanta(self) -> None:
        with self.assertRaises(PaginaInvalida):
            LinhaLida.de_json(self._linha(procedencia_em=[[0, 3, "chute"]]))

    def test_intervalo_invertido_levanta(self) -> None:
        with self.assertRaises(PaginaInvalida):
            LinhaLida.de_json(self._linha(procedencia_em=[[3, 0, "glifo"]]))
        with self.assertRaises(PaginaInvalida):
            LinhaLida.de_json(self._linha(confianca_em=[[-1, 2, 0.5]]))

    def test_confianca_que_nao_e_numero_levanta(self) -> None:
        with self.assertRaises(PaginaInvalida):
            LinhaLida.de_json(self._linha(confianca_em=[[0, 3, "alta"]]))
        with self.assertRaises(PaginaInvalida):
            LinhaLida.de_json(self._linha(confianca_em=[[0, 3]]))

    def test_ausente_e_vazio(self) -> None:
        linha = LinhaLida.de_json(self._linha())
        self.assertEqual((linha.procedencia_em, linha.confianca_em), ((), ()))


class ALeituraPreencheTests(_ComLivro):
    """Afirmado pelo efeito, na `PaginaLida` que sai de `ler_pagina`."""

    def cruas(self, *linhas: str) -> list[Any]:
        """As linhas pedidas e o resto da folha: com menos, a guarda acusa leitura parcial e a fusão não roda."""
        todas = [*linhas, *([LINHA] * (self.linhas_do_pdf - len(linhas)))]
        return [_crua(t, 50 + 18 * k) for k, t in enumerate(todas)]

    def _fundida(self, cruas: Sequence[Any], *lidas: str | None) -> list[LinhaLida]:
        do_leitor = [*lidas, *([LINHA] * (self.linhas_do_pdf - len(lidas)))]
        return _linhas(self.ler("fusao", cruas, leitor_de_linha=_Falso(linhas=do_leitor, confianca=0.8)))

    def test_a_linha_toda_do_tesseract_e_do_tesseract(self) -> None:
        linhas = self._fundida(self.cruas("tne wbite knlght wins a pawn"), "the white knight wins a pawn")
        self.assertEqual(linhas[0].texto, "the white knight wins a pawn")
        self.assertEqual(linhas[0].procedencia, "tesseract")
        self.assertEqual(linhas[0].procedencia_em, (), "uma procedência só não pede detalhe: o campo da linha já diz")
        self.assertEqual(linhas[0].confianca_em[0], (0, 3, 0.8))

    def test_a_linha_mista_leva_a_menos_confiavel_e_diz_onde(self) -> None:
        linhas = self._fundida(self.cruas("the ♘f3 wins a pawn"), "the Af3 wins a pawn")
        self.assertEqual(linhas[0].texto, "the ♘f3 wins a pawn")
        self.assertEqual(linhas[0].procedencia, "glifo")
        self.assertEqual(linhas[0].procedencia_em, ((0, 3, "tesseract"), (4, 7, "glifo"), (8, 19, "tesseract")))

    def test_a_linha_que_o_leitor_nao_leu_fica_do_glifo(self) -> None:
        linhas = self._fundida(self.cruas("wbite wlns", "bl4ck loses"), None, "black loses")
        self.assertEqual([ln.procedencia for ln in linhas][:2], ["glifo", "tesseract"])
        self.assertEqual(linhas[0].procedencia_em, ())

    def test_o_motor_de_glifo_nao_ganha_detalhe(self) -> None:
        """Sem segundo leitor, a faixa do bloco é a de sempre, e nada do que está na tela muda."""
        linhas = _linhas(self.ler("glifo", self.boas()))
        self.assertEqual({(ln.procedencia, ln.procedencia_em, ln.confianca_em) for ln in linhas}, {("glifo", (), ())})

    def test_a_juncao_de_hifen_leva_os_intervalos_junto(self) -> None:
        primeira = LinhaLida(
            "the good em-", CAIXA, procedencia="glifo", procedencia_em=((0, 3, "glifo"), (4, 12, "tesseract")), confianca_em=((4, 12, 0.7),)
        )
        segunda = LinhaLida(
            "barrassment ♘f3", CAIXA, procedencia="glifo", procedencia_em=((0, 11, "tesseract"), (12, 15, "glifo")), confianca_em=((0, 11, 0.6),)
        )
        juntas = leitor._sem_hifen_de_quebra([primeira, segunda], frozenset({"embarrassment"}))  # noqa: SLF001
        self.assertNotEqual(juntas[0].texto, primeira.texto, "a junção é o que este teste exercita")
        for linha in juntas:
            for _inicio, fim, _quem in linha.procedencia_em:
                self.assertLessEqual(fim, len(linha.texto), linha.texto)
        self.assertEqual(juntas[0].procedencia_no(juntas[0].texto.index("good")), "tesseract")
        self.assertEqual(juntas[1].procedencia_no(juntas[1].texto.index("♘")), "glifo")
        # Quase toda a palavra juntada veio da outra linha: o trecho não a alcança, e vale o resumo, que é o pior.
        self.assertEqual(juntas[0].procedencia_no(juntas[0].texto.index("embarrassment")), "glifo")
        self.assertEqual(juntas[0].confianca_em[0][2], 0.7)

    def test_o_espacado_leva_os_intervalos_junto(self) -> None:
        linhas = self._fundida(self.cruas("a t t a c k wins ♘f3 a pawn"), "a t t a c k wins Af3 a pawn")
        linha = linhas[0]
        self.assertEqual(linha.texto, "attack wins ♘f3 a pawn")
        self.assertEqual(linha.procedencia_no(linha.texto.index("♘")), "glifo")
        self.assertEqual(linha.procedencia_no(linha.texto.index("wins")), "tesseract")
        self.assertEqual(linha.procedencia_no(2), "tesseract")
        self.assertIn("wins", [linha.texto[a:b] for a, b, _ in linha.confianca_em])

    def test_a_reserva_diz_de_quem_e_a_linha(self) -> None:
        palavras = [tesseract.Palavra("white", 0.9, (200, 200, 400, 240), bloco=1, paragrafo=1, linha=1)]
        lida = self.ler("glifo", [_crua("h", 50)], leitor_de_linha=_Falso(folha=palavras), reserva=True)
        self.assertEqual({ln.procedencia for ln in _linhas(lida)}, {"tesseract"})

    def test_na_camada_a_palavra_trocada_e_do_tesseract(self) -> None:
        """A linha da camada com uma palavra do Tesseract não é mais registro: `exigir_documento_cego` precisa ver."""
        palavras = [
            camada_prosa.PalavraDaCamada(p, (60.0 + 22 * k, 58.0, 80.0 + 22 * k, 66.0), p == "knight")
            for k, p in enumerate(LINHA.split())
        ]
        leitura = tesseract.Palavra("knight!", 0.9, (int(104 * ESCALA), int(58 * ESCALA), int(124 * ESCALA), int(66 * ESCALA)))
        with mock.patch.object(camada_prosa, "palavras_da_folha", return_value=palavras):
            lida = self.ler("camada_prosa", [_crua("h", 50)], leitor_de_linha=_Falso(folha=[leitura]), reserva=True)
        linha = next(ln for ln in _linhas(lida) if "knight!" in ln.texto)
        self.assertEqual(linha.procedencia, "tesseract")
        self.assertEqual(linha.procedencia_no(linha.texto.index("white")), "camada")
        self.assertEqual(linha.procedencia_no(linha.texto.index("knight!")), "tesseract")
        self.assertEqual(linha.confianca, 1.0, "a confiança da linha continua a da camada: a marca é por palavra")


class AAbaLeTests(unittest.TestCase):
    """O que o editor desenha sai dos campos: corrida por procedência, e faixa por palavra."""

    def test_o_texto_nao_muda_um_caractere(self) -> None:
        pag = _pagina_com(_mista(), LinhaLida("black loses", CAIXA, procedencia="tesseract"))
        self.assertEqual(rico.de_pagina(pag).para_texto(), "".join(s.texto for s in documento.segmentos(pag)))

    def test_cada_corrida_diz_de_quem_e(self) -> None:
        doc = rico.de_pagina(_pagina_com(_mista()))
        self.assertEqual(
            [(c.texto, c.procedencia) for c in doc.corridas],
            [("the ", "tesseract"), ("wbite", "glifo"), (" ", "glifo"), ("wins", "tesseract")],
        )

    def test_a_faixa_marca_a_palavra_e_nao_o_bloco(self) -> None:
        """É a saída do item: a confiança baixa de `wbite` pinta `wbite`, e nunca o parágrafo."""
        doc = rico.de_pagina(_pagina_com(_mista()))
        marcadas = [c.texto.strip() for c in doc.corridas if c.faixa == documento.REVISAR]
        self.assertEqual(marcadas, ["wbite"])
        self.assertNotIn(documento.REVISAR, {c.faixa for c in doc.corridas if " " in c.texto.strip()})

    def test_com_a_marca_ligada_quem_manda_e_o_teto_da_s718(self) -> None:
        """A marca ranqueada tem teto de 5%. O sinal cru da confiança não pinta por cima dela."""
        linha = _mista()
        doc = rico.de_pagina(_pagina_com(linha, marca_por_palavra=True))
        self.assertEqual([c for c in doc.corridas if c.faixa == documento.REVISAR], [])

    def test_a_contagem_da_barra_le_o_detalhe(self) -> None:
        contagem = documento.contagem_por_faixa(_pagina_com(_mista()))
        self.assertEqual(contagem[documento.REVISAR], 1)
        limpa = LinhaLida("the white wins", CAIXA, confianca=0.1, procedencia="tesseract", confianca_em=((0, 14, 0.95),))
        self.assertEqual(documento.contagem_por_faixa(_pagina_com(limpa))[documento.TRANQUILO], 1)

    def test_a_barra_diz_de_quem_e_o_texto(self) -> None:
        resumo = documento.resumo(_pagina_com(_mista()))
        self.assertIn("texto: 58% tesseract, 42% glifo", resumo)
        self.assertNotIn("texto:", documento.resumo(_pagina_com(LinhaLida("abc", CAIXA, procedencia="glifo"))))

    def test_o_caractere_de_cada_procedencia(self) -> None:
        pag = _pagina_com(_mista(), LinhaLida("black loses", CAIXA, procedencia="tesseract"))
        self.assertEqual(pag.caracteres_por_procedencia(), {"tesseract": 7 + 10, "glifo": 5})


class AExportacaoLeTests(unittest.TestCase):
    def test_o_txt_sai_byte_a_byte_igual(self) -> None:
        pag = _pagina_com(_mista())
        doc = rico.de_pagina(pag)
        self.assertEqual(exportacao.exportar(doc, exportacao.Texto()).conteudo, documento.texto_para_arquivo(pag))

    def test_o_html_diz_de_quem_e_a_palavra_e_pinta_a_palavra(self) -> None:
        html = exportacao.exportar(rico.de_pagina(_pagina_com(_mista())), exportacao.Html()).conteudo
        self.assertIn('data-procedencia="tesseract"', html)
        self.assertIn('class="faixa-revisar"', html)
        self.assertRegex(html, r'<span class="faixa-revisar"[^>]*>wbite')

    def test_folha_sem_tesseract_nao_muda_o_html(self) -> None:
        html = exportacao.exportar(rico.de_pagina(_pagina_com(LinhaLida("abc", CAIXA, procedencia="glifo"))), exportacao.Html()).conteudo
        self.assertNotIn("data-procedencia", html)

    def test_o_relatorio_conta_por_procedencia(self) -> None:
        relatorio = exportacao.exportar(rico.de_pagina(_pagina_com(_mista())), exportacao.Texto())
        self.assertEqual(relatorio.procedencias, {"tesseract": 7, "glifo": 5})


class OParTocadoDizQuemErrouTests(unittest.TestCase):
    """`Na fusão, o motor sai glifo` era a ressalva da S-762, à espera deste item."""

    def _corrigido(self, pag: PaginaLida, antes: str, depois: str) -> rico.DocumentoRico:
        doc = rico.de_pagina(pag)
        corridas = [
            rico.Corrida(c.texto.replace(antes, depois), c.atributos, c.faixa, c.bloco, c.procedencia, c.tipo) for c in doc.corridas
        ]
        return rico.DocumentoRico(corridas=tuple(corridas), origem=pag)

    def test_a_palavra_do_glifo_num_bloco_misto(self) -> None:
        pares = dado_corrigido.pares_tocados(self._corrigido(_pagina_com(_mista(), modelo="abc123"), "wbite", "white"))
        self.assertEqual([(p.antes, p.motor, p.modelo) for p in pares], [("wbite", "glifo", "abc123")])
        self.assertEqual(pares[0].procedencia, "corrigido_de:glifo@abc123")

    def test_a_palavra_do_tesseract_nao_acusa_o_classificador(self) -> None:
        pares = dado_corrigido.pares_tocados(self._corrigido(_pagina_com(_mista(), modelo="abc123"), "wins", "won"))
        self.assertEqual([(p.antes, p.motor, p.modelo) for p in pares], [("wins", "tesseract", "")])
        self.assertTrue(pares[0].procedencia.startswith("corrigido_de:tesseract@"))

    def test_a_palavra_da_camada_num_bloco_misto_nao_vira_par(self) -> None:
        """A camada é o que o editor escreveu: não há motor a acusar, como num bloco inteiro da camada."""
        linha = LinhaLida(
            "the knigth wins", CAIXA, procedencia="tesseract", procedencia_em=((0, 3, "camada"), (4, 10, "tesseract"), (11, 15, "camada"))
        )
        self.assertEqual(dado_corrigido.pares_tocados(self._corrigido(_pagina_com(linha), "wins", "won")), ())
        self.assertEqual(len(dado_corrigido.pares_tocados(self._corrigido(_pagina_com(linha), "knigth", "knight"))), 1)

    def test_a_folha_com_tesseract_nao_e_verdade_cega(self) -> None:
        doc = rico.de_pagina(_pagina_com(LinhaLida("abc", CAIXA, procedencia="tesseract")))
        with self.assertRaises(dado_corrigido.FolhaAncorada):
            dado_corrigido.exigir_documento_cego(doc, onde="teste")

    def test_a_marcacao_da_mao_vale_para_as_corridas_novas(self) -> None:
        """`com_procedencia_humana` é por bloco, e continua sendo com o bloco partido em três corridas."""
        doc = correcao.com_procedencia_humana(self._corrigido(_pagina_com(_mista()), "wbite", "white"))
        self.assertEqual({c.procedencia for c in doc.corridas}, {"humano"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
