"""A pergunta de documento sobre estilo é feita uma vez por livro, e não uma por folha (S-313).

**O custo que isto tira.** `camada.documento_registra` abre uma amostra de páginas e varre os
spans delas -- é a pergunta que separa "aqui não tem itálico" de "este livro não registra
itálico", e sem ela a S-237 não distingue `False` de `None`. Só que `ler_pagina` a fazia **duas
vezes por folha**, uma para o peso e outra para o pendor, e ela não tinha memória nenhuma.

Medido no acervo com o `.venv` do projeto:

| livro | folhas | primeira folha | folhas seguintes |
|---|---|---|---|
| A Matter of Endgame Technique | 898 | 2.606 ms | 0,110 ms |
| Excelling at chess calculation | 193 | 2.197 ms | 0,094 ms |

Na varredura de texto do primeiro, são ~39 min que deixam de ser pagos.

**A parte difícil é a chave, e é o que estes testes travam.** `e_do_estilo` é uma função, e duas
funções não têm chave comum -- daí a `marca`. E `PdfSource` aceita `bytes` e um documento já
aberto: nesses casos `doc.name` é vazio, e um cache chaveado por nome vazio devolveria a
resposta de **outro** documento. Sem identidade no disco, sem memória.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.text import camada


class _Pagina:
    def __init__(self, spans: list[dict]) -> None:
        self._spans = spans

    def get_text(self, _modo: str) -> dict:
        return {"blocks": [{"lines": [{"spans": self._spans}]}]}


class _Documento:
    """Um PDF de mentira que **conta** quantas páginas foram abertas."""

    def __init__(self, paginas: list[_Pagina], *, name: str = "") -> None:
        self._paginas = paginas
        self.name = name
        self.page_count = len(paginas)
        self.aberturas = 0

    def __getitem__(self, indice: int) -> _Pagina:
        self.aberturas += 1
        return self._paginas[indice]


def _span(*, font: str) -> dict:
    return {"font": font, "flags": 0, "bbox": (0.0, 0.0, 10.0, 10.0), "text": "x"}


def _e_italico(span: dict) -> bool:
    return "Italic" in str(span.get("font", ""))


class MemoriaPorLivroTests(unittest.TestCase):
    def setUp(self) -> None:
        camada.esquecer_documentos()
        self.addCleanup(camada.esquecer_documentos)

    def _livro(self, tmp: str, *, italico: bool) -> _Documento:
        fonte = "Times-Italic" if italico else "Times"
        return _Documento([_Pagina([_span(font=fonte)]) for _ in range(8)], name=tmp)

    def test_o_livro_do_disco_e_perguntado_uma_vez_so(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as arquivo:
            arquivo.write(b"%PDF-1.4\n")
            caminho = arquivo.name
        doc = self._livro(caminho, italico=True)

        camada.documento_registra(doc, _e_italico, marca="italico")
        depois_da_primeira = doc.aberturas
        for _ in range(20):
            camada.documento_registra(doc, _e_italico, marca="italico")

        self.assertGreater(depois_da_primeira, 0)
        self.assertEqual(doc.aberturas, depois_da_primeira, "a pergunta foi refeita")

    def test_o_documento_sem_arquivo_nunca_e_memorizado(self) -> None:
        """`PdfSource` aceita `bytes` e um documento já aberto, e ali `name` é vazio.

        Um cache chaveado por nome vazio faria o segundo livro herdar a resposta do primeiro --
        e a resposta muda o significado de toda linha sem itálico da folha.
        """
        com = self._livro("", italico=True)
        sem = self._livro("", italico=False)

        self.assertTrue(camada.documento_registra(com, _e_italico, marca="italico"))
        self.assertFalse(camada.documento_registra(sem, _e_italico, marca="italico"))

    def test_sem_marca_nao_ha_memoria(self) -> None:
        """O padrão é não memorizar: nenhum chamador ganha cache sem pedir por nome."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as arquivo:
            arquivo.write(b"%PDF-1.4\n")
            caminho = arquivo.name
        doc = self._livro(caminho, italico=True)

        camada.documento_registra(doc, _e_italico)
        primeira = doc.aberturas
        camada.documento_registra(doc, _e_italico)

        self.assertGreater(doc.aberturas, primeira)

    def test_duas_marcas_nao_se_confundem(self) -> None:
        """Peso e pendor têm respostas diferentes sobre o mesmo livro, e a chave as separa."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as arquivo:
            arquivo.write(b"%PDF-1.4\n")
            caminho = arquivo.name
        doc = self._livro(caminho, italico=True)

        self.assertTrue(camada.documento_registra(doc, _e_italico, marca="italico"))
        self.assertFalse(
            camada.documento_registra(doc, lambda s: "Bold" in str(s.get("font", "")), marca="negrito")
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
