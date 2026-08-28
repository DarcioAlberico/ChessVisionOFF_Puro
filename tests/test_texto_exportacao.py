"""A exportação do editor: um lugar só decide o que cada formato faz (S-250/S-251).

**O que estes testes travam é a perda silenciosa.** O `.txt` não tem negrito; a exportação não finge
que tem e **conta** quantos atributos caíram. Uma perda calada num formato de texto é o que faz
alguém descobrir três meses depois que a exportação apagou o trabalho -- e o `.txt` é o formato mais
usado dos quatro.

O segundo grupo é a trava de não-regressão: o `.txt` sai **byte a byte** igual ao que a aba já
gravava desde a S-211.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from chess_diagram_ocr.text import documento, exportacao, rico
from chess_diagram_ocr.text.pagina import BlocoDeDiagrama, BlocoDeTexto, Coluna, LinhaLida, PaginaLida

MODULO = Path(exportacao.__file__)


def _pagina(*blocos: object) -> PaginaLida:
    return PaginaLida(
        documento="livro.pdf",
        pagina=57,
        colunas=(Coluna(indice=0, blocos=tuple(blocos)),),  # type: ignore[arg-type]
    )


def _texto(conteudo: str, confianca: float = 1.0, procedencia: str = "camada") -> BlocoDeTexto:
    return BlocoDeTexto.de_linhas(
        [LinhaLida(conteudo, (0.0, 0.0, 100.0, 9.0), confianca, procedencia)]  # type: ignore[arg-type]
    )


def _com_tudo() -> rico.DocumentoRico:
    """Um documento com um atributo de cada, para as perdas terem o que contar."""
    doc = rico.de_pagina(_pagina(_texto("Uma frase com <isto> & aquilo."), _texto("Outra frase.")))
    doc = rico.alternar(doc, 0, 3, "negrito")
    doc = rico.alternar(doc, 4, 9, "italico")
    doc = rico.aplicar(doc, 10, 14, sublinhado=True, cor="nota", realce="destaque")
    return rico.aplicar_estilo(doc, 0, 3, "titulo")


class TodosSaemDoMesmoDocumentoTests(unittest.TestCase):
    def test_os_formatos_saem_do_mesmo_documento(self) -> None:
        doc = _com_tudo()
        for extensao in exportacao.FORMATOS:
            with self.subTest(formato=extensao):
                relatorio = exportacao.exportar(doc, exportacao.formato_de(extensao))
                self.assertTrue(relatorio.conteudo.strip())

    def test_a_marca_aparece_nos_quatro_formatos(self) -> None:
        """**A marca nunca desaparece**, nem quando a imagem entra: sem ela, a primeira edição
        perderia o diagrama (`text/documento.py`)."""
        doc = rico.de_pagina(_pagina(_texto("antes"), BlocoDeDiagrama(indice=2, bbox=(0.0, 0.0, 9.0, 9.0))))
        for extensao in exportacao.FORMATOS:
            with self.subTest(formato=extensao):
                saida = exportacao.exportar(doc, exportacao.formato_de(extensao)).conteudo
                self.assertIn("[Diagrama 3]", saida)

    def test_a_marca_fica_mesmo_com_a_imagem(self) -> None:
        doc = rico.de_pagina(_pagina(BlocoDeDiagrama(indice=0, bbox=(0.0, 0.0, 9.0, 9.0))))
        recortes = {0: Path("diagrama_01.png")}
        for extensao in (".md", ".html"):
            with self.subTest(formato=extensao):
                saida = exportacao.exportar(doc, exportacao.formato_de(extensao), recortes=recortes).conteudo
                self.assertIn("[Diagrama 1]", saida)
                self.assertIn("diagrama_01.png", saida)

    def test_exportar_duas_vezes_da_o_mesmo_byte(self) -> None:
        """Sem data no corpo do arquivo: duas exportações do mesmo documento têm de diffar zero."""
        doc = _com_tudo()
        for extensao in exportacao.FORMATOS:
            with self.subTest(formato=extensao):
                formato = exportacao.formato_de(extensao)
                primeira = exportacao.exportar(doc, formato).conteudo
                segunda = exportacao.exportar(doc, formato).conteudo
                self.assertEqual(primeira, segunda)

    def test_o_modulo_nao_importa_tkinter(self) -> None:
        arvore = ast.parse(MODULO.read_text(encoding="utf-8"))
        importados: set[str] = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                importados.update(alias.name.split(".")[0] for alias in no.names)
            elif isinstance(no, ast.ImportFrom) and no.module:
                importados.add(no.module.split(".")[0])
        self.assertNotIn("tkinter", importados)


class PerdaExplicitaTests(unittest.TestCase):
    def test_cada_formato_declara_o_que_perde(self) -> None:
        """A tabela atributo × formato é total: `False` é resposta válida e **explícita**."""
        tabela = exportacao.suporte_por_formato()
        self.assertEqual(set(tabela), set(exportacao.FORMATOS))
        for extensao, atributos in tabela.items():
            with self.subTest(formato=extensao):
                self.assertEqual(set(atributos), set(exportacao.ATRIBUTOS))

    def test_o_relatorio_conta_as_perdas(self) -> None:
        doc = _com_tudo()
        txt = exportacao.exportar(doc, exportacao.Texto())
        self.assertTrue(txt.perdeu)
        self.assertIn("negrito", txt.perdas)
        self.assertIn("cor", txt.perdas)
        html = exportacao.exportar(doc, exportacao.Html())
        self.assertFalse(html.perdeu, html.perdas)

    def test_o_md_declara_a_perda_de_cor(self) -> None:
        """Cor de autor não tem sintaxe em Markdown, e a faixa também não."""
        doc = rico.aplicar(rico.de_texto("um trecho"), 0, 9, cor="nota")
        relatorio = exportacao.exportar(doc, exportacao.Markdown())
        self.assertEqual(relatorio.perdas.get("cor"), 1)

    def test_o_md_declara_a_perda_do_estilo_que_ele_nao_escreve(self) -> None:
        """`suporta` dizia "estilo: sim" por causa do `# ` do título (S-339).

        Legenda, notação e prosa não têm sintaxe no Markdown: saíam como texto comum e o relatório
        dizia "perdido: nada". Título continua sendo escrito, e continua sem perda.
        """
        legenda = rico.aplicar_estilo(rico.de_texto("uma legenda"), 0, 11, "legenda")
        self.assertEqual(exportacao.exportar(legenda, exportacao.Markdown()).perdas.get("estilo"), 1)

        titulo = rico.aplicar_estilo(rico.de_texto("um título"), 0, 9, "titulo")
        self.assertIsNone(exportacao.exportar(titulo, exportacao.Markdown()).perdas.get("estilo"))

    def test_o_rtf_conta_o_recorte_que_ele_joga_fora(self) -> None:
        """O RTF não carrega imagem, e passar o recorte a ele zerava `sem_recorte`: o relatório
        dizia "nenhum diagrama sem recorte" sobre um arquivo em que nenhum tem imagem (S-341)."""
        from pathlib import Path as _Path

        doc = rico.de_pagina(_pagina(_texto("antes"), BlocoDeDiagrama(indice=0), _texto("depois")))
        diagrama = next(c for c in doc.corridas if c.e_diagrama)

        relatorio = exportacao.exportar(doc, exportacao.Rtf(), recortes={diagrama.bloco: _Path("d.png")})

        self.assertEqual(relatorio.sem_recorte, 0, "o recorte existia")
        self.assertIn("não carrega", " ".join(relatorio.avisos))

    def test_o_md_com_recorte_nao_avisa_nada_disso(self) -> None:
        """A contrapartida: quem carrega a imagem não avisa perda nenhuma."""
        from pathlib import Path as _Path

        doc = rico.de_pagina(_pagina(BlocoDeDiagrama(indice=0)))
        diagrama = next(c for c in doc.corridas if c.e_diagrama)

        relatorio = exportacao.exportar(doc, exportacao.Markdown(), recortes={diagrama.bloco: _Path("d.png")})

        self.assertNotIn("não carrega", " ".join(relatorio.avisos))
        self.assertIn("d.png", relatorio.conteudo)

    def test_o_relatorio_avisa_o_que_nao_e_perda(self) -> None:
        doc = rico.inserir(rico.de_texto("prosa"), 5, "♞", fora_do_modelo=True)
        avisos = " ".join(exportacao.exportar(doc, exportacao.Html()).avisos)
        self.assertIn("modelo não lê", avisos)

    def test_o_atributo_e_derivado_de_Atributos(self) -> None:
        """Recopiar a lista faria um atributo novo entrar sem nenhum formato dizer o que faz com ele."""
        from dataclasses import fields

        self.assertEqual(set(exportacao.ATRIBUTOS), {c.name for c in fields(rico.Atributos)})


class TxtIdenticoTests(unittest.TestCase):
    def test_o_txt_sai_identico_ao_de_hoje(self) -> None:
        """A trava de não-regressão: `cabecalho + conteudo.strip() + quebra`, como desde a S-211."""
        pagina = _pagina(_texto("Uma frase."), _texto("Outra."))
        doc = rico.de_pagina(pagina)
        de_antes = (
            documento.texto_para_arquivo(pagina).split("\n\n", 1)[0]
            + "\n\n"
            + doc.para_texto().strip()
            + "\n"
        )
        self.assertEqual(exportacao.exportar(doc, exportacao.Texto()).conteudo, de_antes)

    def test_o_txt_nao_carrega_marca_de_formato(self) -> None:
        doc = rico.alternar(rico.de_texto("negrito puro"), 0, 7, "negrito")
        saida = exportacao.exportar(doc, exportacao.Texto()).conteudo
        self.assertNotIn("*", saida)
        self.assertIn("negrito puro", saida)


class MarkdownTests(unittest.TestCase):
    def test_o_md_ida_e_volta_preserva_o_atributo(self) -> None:
        """Negrito e itálico saem em `**` e `*`, que é o que faz o `.md` diffar e reabrir."""
        doc = rico.alternar(rico.de_texto("negrito e italico"), 0, 7, "negrito")
        doc = rico.alternar(doc, 10, 17, "italico")
        saida = exportacao.exportar(doc, exportacao.Markdown()).conteudo
        self.assertIn("**negrito**", saida)
        self.assertIn("*italico*", saida)

    def test_o_titulo_vira_cabecalho(self) -> None:
        doc = rico.aplicar_estilo(rico.de_texto("Um título"), 0, 9, "titulo")
        self.assertIn("# Um título", exportacao.exportar(doc, exportacao.Markdown()).conteudo)

    def test_a_marcacao_nao_engole_o_espaco(self) -> None:
        """`**negrito** ` e não `**negrito **`: a segunda forma o Markdown não lê como negrito."""
        doc = rico.aplicar(rico.de_texto("negrito e resto"), 0, 8, negrito=True)
        self.assertIn("**negrito** ", exportacao.exportar(doc, exportacao.Markdown()).conteudo)


class HtmlTests(unittest.TestCase):
    def test_o_html_escapa_o_que_veio_do_ocr(self) -> None:
        """A S-211 mediu 96 caracteres espúrios em 13 páginas, e um `<` engole o resto do arquivo."""
        doc = rico.de_texto("um <script> e & outro")
        saida = exportacao.exportar(doc, exportacao.Html()).conteudo
        self.assertIn("&lt;script&gt;", saida)
        self.assertNotIn("<script>", saida)

    def test_o_html_nao_depende_de_arquivo_externo(self) -> None:
        """Abre no navegador sem nada ao lado, além das imagens de diagrama."""
        saida = exportacao.exportar(_com_tudo(), exportacao.Html()).conteudo
        self.assertIn("<style>", saida)
        self.assertNotIn("<link", saida)
        self.assertNotIn("<script", saida)

    def test_o_html_avisa_sobre_a_fonte_de_figurina(self) -> None:
        """`♘` depende do que a máquina de destino tem instalado, e nenhuma fonte é embutida."""
        saida = exportacao.exportar(rico.de_texto("1.♘f3"), exportacao.Html()).conteudo
        self.assertIn("fonte", saida.lower())
        self.assertIn("figurina", saida.lower())

    def test_nenhuma_cor_literal_no_exportador(self) -> None:
        """Toda cor da saída vem de `tokens.cor`, passada de fora -- o módulo não conhece nenhuma."""
        arvore = ast.parse(MODULO.read_text(encoding="utf-8"))
        literais = [
            no.value
            for no in ast.walk(arvore)
            if isinstance(no, ast.Constant)
            and isinstance(no.value, str)
            and no.value.startswith("#")
            and len(no.value) in (4, 7)
        ]
        self.assertEqual(literais, [])

    def test_a_cor_da_saida_e_a_que_veio_de_fora(self) -> None:
        doc = rico.aplicar(rico.de_texto("um trecho"), 0, 9, cor="nota")
        saida = exportacao.exportar(doc, exportacao.Html(cores={"cor-nota": "#147925"})).conteudo
        self.assertIn("#147925", saida)
        self.assertIn('class="cor-nota"', saida)

    def test_a_faixa_de_confianca_atravessa(self) -> None:
        """O `.html` é o único que mostra o que a aba mostrava -- inclusive a régua do motor."""
        doc = rico.de_pagina(_pagina(_texto("adivinhado", 0.1, "glifo")))
        saida = exportacao.exportar(doc, exportacao.Html()).conteudo
        self.assertIn(f"faixa-{documento.REVISAR}", saida)

    def test_o_html_tem_regra_para_cada_classe_de_estilo_que_emite(self) -> None:
        """Quatro classes `estilo-*` eram emitidas e nenhuma tinha regra na folha (S-340).

        O critério é o dos dois lados: toda classe emitida tem regra, e nenhuma regra existe para
        classe que ninguém emite.
        """
        formato = exportacao.Html()
        emitidas = set()
        for estilo in ("titulo", "prosa", "notacao", "legenda"):
            doc = rico.aplicar_estilo(rico.de_texto("um trecho"), 0, 9, estilo)
            emitidas.update(c for c in formato._classes(doc.corridas[0]) if c.startswith("estilo-"))
        com_regra = {f"{nome}" for nome, _p, _v in formato._regras() if nome.startswith("estilo-")}

        self.assertEqual(emitidas, com_regra)
        self.assertNotIn("estilo-prosa", emitidas, "prosa é o padrão do documento")
        self.assertNotIn("estilo-titulo", emitidas, "título sai como <h2>")

    def test_a_regra_do_estilo_chega_ao_arquivo(self) -> None:
        doc = rico.aplicar_estilo(rico.de_texto("uma legenda"), 0, 11, "legenda")
        conteudo = exportacao.exportar(doc, exportacao.Html()).conteudo
        self.assertIn(".estilo-legenda {", conteudo)
        self.assertIn('class="estilo-legenda"', conteudo)


class FormatoDesconhecidoTests(unittest.TestCase):
    def test_extensao_que_ninguem_escreveu_levanta(self) -> None:
        with self.assertRaises(KeyError):
            exportacao.formato_de(".docx")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
