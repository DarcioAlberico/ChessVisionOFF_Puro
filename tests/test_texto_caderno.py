"""O caderno do livro, puro: uma folha por arquivo, sem poda, achado pelo conteúdo (S-610).

Os critérios de aceite da S-610 em `docs/ROADMAP_MESA_DE_TEXTO.md`, cada um num teste: 300 folhas
deixam 300 arquivos, a gravação interrompida deixa a versão anterior legível, o livro movido e o
livro duplicado abrem um caderno só, e a trava de um processo vivo deixa o segundo só para leitura.
"""

from __future__ import annotations

import os
import shutil
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr.text import arquivo, caderno, rico
from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida


def _pagina(livro: str, folha: int = 0, texto: str = "uma folha lida") -> PaginaLida:
    bloco = BlocoDeTexto.de_linhas([LinhaLida(texto, (0.0, 0.0, 100.0, 9.0), 0.5, "glifo")])  # type: ignore[arg-type]
    return PaginaLida(documento=livro, pagina=folha, colunas=(Coluna(indice=0, blocos=(bloco,)),))


def _doc(livro: Path, folha: int = 0, texto: str = "uma folha lida") -> rico.DocumentoRico:
    return rico.de_pagina(_pagina(str(livro), folha, texto))


def _editado(doc: rico.DocumentoRico, acrescimo: str) -> rico.DocumentoRico:
    fim = len(doc.para_texto())
    return rico.editar(doc, fim, fim, acrescimo)


class _ComLivro(unittest.TestCase):
    def setUp(self) -> None:
        self.raiz = pasta_temporaria(self)
        self.pasta = self.raiz / "cadernos"
        self.livro = self.raiz / "livros" / "Nunn - Understanding.pdf"
        self.livro.parent.mkdir(parents=True)
        self.livro.write_bytes(b"%PDF-1.7\n" + bytes(range(256)) * 64)

    def abrir(self, livro: Path | None = None) -> caderno.Caderno:
        aberto = caderno.abrir(livro or self.livro, pasta=self.pasta)
        assert aberto is not None
        self.addCleanup(aberto.fechar)
        return aberto


class GravarTests(_ComLivro):
    def test_trezentas_folhas_deixam_trezentos_arquivos_e_um_indice(self) -> None:
        livro = self.abrir()
        for folha in range(300):
            self.assertEqual(livro.gravar(_doc(self.livro, folha, f"folha {folha}")), caderno.GRAVADA)
        arquivos = sorted(livro.pasta.glob(f"folha-[0-9][0-9][0-9][0-9]{arquivo.EXTENSAO}"))
        self.assertEqual(len(arquivos), 300, "o caderno podou")
        self.assertEqual(len(caderno.abrir(self.livro, pasta=self.pasta).folhas()), 300)  # type: ignore[union-attr]

    def test_a_folha_volta_igual(self) -> None:
        livro = self.abrir()
        doc = _editado(_doc(self.livro, 4), " corrigida")
        livro.gravar(doc, correcoes=1)
        self.assertEqual(self.abrir().folha(4), doc)
        self.assertEqual(livro.estado(4).estado, caderno.EDITADA)  # type: ignore[union-attr]
        self.assertEqual(livro.estado(4).correcoes, 1)  # type: ignore[union-attr]

    def test_gravar_o_mesmo_nao_reescreve(self) -> None:
        livro = self.abrir()
        doc = _doc(self.livro)
        livro.gravar(doc)
        self.assertFalse(livro.difere(doc))
        self.assertEqual(livro.gravar(doc), caderno.IGUAL)
        self.assertTrue(livro.difere(_editado(doc, "!")))

    def test_gravacao_interrompida_deixa_a_versao_anterior_legivel(self) -> None:
        livro = self.abrir()
        livro.gravar(_doc(self.livro, 0, "a versão boa"))
        with mock.patch.object(caderno.os, "replace", side_effect=OSError("disco cheio")):
            with self.assertRaises(OSError):
                livro.gravar(_doc(self.livro, 0, "a versão nova"))
        self.assertIn("a versão boa", arquivo.carregar(livro.caminho(0)).para_texto())
        self.assertEqual(list(livro.pasta.glob(".*.tmp")), [], "o temporário ficou para trás")

    def test_a_folha_vazia_nao_vai_por_cima_da_que_tem_texto(self) -> None:
        livro = self.abrir()
        doc = _doc(self.livro, 2, "texto que custou")
        livro.gravar(doc)
        vazia = rico.editar(doc, 0, len(doc.para_texto()), "")
        self.assertEqual(livro.gravar(vazia), caderno.RECUSADA_VAZIA)
        self.assertIn("texto que custou", livro.folha(2).para_texto())  # type: ignore[union-attr]

    def test_documento_sem_folha_nao_tem_caderno(self) -> None:
        self.assertEqual(self.abrir().gravar(rico.DocumentoRico()), caderno.SEM_FOLHA)


class AnteriorTests(_ComLivro):
    def test_a_primeira_gravacao_da_visita_guarda_a_folha_de_antes(self) -> None:
        livro = self.abrir()
        livro.gravar(_doc(self.livro, 0, "como estava"))
        livro.visitar(0)
        livro.gravar(_doc(self.livro, 0, "primeira mudança"))
        livro.gravar(_doc(self.livro, 0, "segunda mudança"))
        self.assertIn("como estava", livro.anterior(0).para_texto())  # type: ignore[union-attr]
        self.assertIn("segunda", livro.folha(0).para_texto())  # type: ignore[union-attr]

    def test_ler_de_novo_guarda_a_corrigida_como_anterior_e_a_leitura_como_lida(self) -> None:
        livro = self.abrir()
        livro.guardar_leitura(_doc(self.livro, 0, "lida pelo glifo"), motor="glifo", modo_bloco=False)
        livro.gravar(_doc(self.livro, 0, "corrigida à mão"), correcoes=3)
        livro.guardar_leitura(_doc(self.livro, 0, "lida pelo auto"), motor="auto", modo_bloco=True)
        self.assertIn("corrigida", livro.anterior(0).para_texto())  # type: ignore[union-attr]
        self.assertIn("auto", livro.lida(0).para_texto())  # type: ignore[union-attr]
        estado = livro.estado(0)
        assert estado is not None
        self.assertEqual((estado.estado, estado.motor, estado.modo_bloco, estado.correcoes), (caderno.LIDA, "auto", True, 0))


class IdentidadeTests(_ComLivro):
    def test_mover_o_pdf_abre_o_caderno_de_antes(self) -> None:
        livro = self.abrir()
        livro.gravar(_doc(self.livro, 0, "corrigida antes da mudança"))
        livro.fechar()
        movido = self.raiz / "outra pasta" / "renomeado.pdf"
        movido.parent.mkdir()
        shutil.move(self.livro, movido)
        reaberto = self.abrir(movido)
        self.assertIn("corrigida", reaberto.folha(0).para_texto())  # type: ignore[union-attr]
        self.assertEqual(reaberto.apelidos, (str(self.livro), str(movido)))

    def test_o_mesmo_livro_em_duas_pastas_abre_um_caderno(self) -> None:
        copia = self.raiz / "copia" / self.livro.name
        copia.parent.mkdir()
        shutil.copy(self.livro, copia)
        um = self.abrir()
        um.fechar()
        self.assertEqual(self.abrir(copia).pasta, um.pasta)
        self.assertEqual(len(list(self.pasta.iterdir())), 1)

    def test_livros_diferentes_tem_cadernos_diferentes(self) -> None:
        outro = self.raiz / "livros" / "outro.pdf"
        outro.write_bytes(b"%PDF-1.7\n outro livro")
        self.assertNotEqual(self.abrir().pasta, self.abrir(outro).pasta)

    def test_livro_que_nao_abre_nao_tem_caderno(self) -> None:
        self.assertIsNone(caderno.abrir(self.raiz / "nao existe.pdf", pasta=self.pasta))


class IndiceTests(_ComLivro):
    def test_marcar_conferida_grava_o_indice(self) -> None:
        livro = self.abrir()
        livro.gravar(_doc(self.livro, 7))
        self.assertTrue(livro.marcar(7, caderno.CONFERIDA))
        livro.fechar()
        self.assertEqual(self.abrir().conferidas(), 1)

    def test_indice_corrompido_e_refeito_pelas_folhas(self) -> None:
        livro = self.abrir()
        livro.gravar(_doc(self.livro, 0))
        livro.gravar(_doc(self.livro, 5))
        livro.fechar()
        (livro.pasta / "indice.json").write_text("{ isto não é json", encoding="utf-8")
        self.assertEqual([f.pagina for f in self.abrir().folhas()], [0, 5])

    def test_rascunho_mais_novo_entra_e_o_mais_velho_nao(self) -> None:
        livro = self.abrir()
        self.assertTrue(livro.trazer_rascunho(_doc(self.livro, 4, "do rascunho"), datetime.now() - timedelta(days=1)))
        livro.gravar(_doc(self.livro, 6, "do caderno"))
        self.assertFalse(livro.trazer_rascunho(_doc(self.livro, 6, "rascunho velho"), datetime.now() - timedelta(days=2)))
        self.assertIn("do caderno", livro.folha(6).para_texto())  # type: ignore[union-attr]


class TravaTests(_ComLivro):
    def test_trava_de_processo_vivo_abre_so_para_leitura(self) -> None:
        primeiro = self.abrir()
        primeiro.fechar()
        # O pai deste processo está vivo e não é este: é a outra janela.
        (primeiro.pasta / "caderno.lock").write_text(str(os.getppid()), encoding="utf-8")
        segundo = self.abrir()
        self.assertTrue(segundo.somente_leitura)
        self.assertIn("só para leitura", segundo.motivo)
        self.assertEqual(segundo.gravar(_doc(self.livro)), caderno.SOMENTE_LEITURA)
        self.assertFalse(segundo.caminho(0).exists())

    def test_trava_de_processo_morto_e_retomada(self) -> None:
        primeiro = self.abrir()
        primeiro.fechar()
        (primeiro.pasta / "caderno.lock").write_text("999999999", encoding="utf-8")
        segundo = self.abrir()
        self.assertFalse(segundo.somente_leitura)
        self.assertEqual(segundo.gravar(_doc(self.livro)), caderno.GRAVADA)

    def test_fechar_solta_a_trava(self) -> None:
        livro = self.abrir()
        self.assertTrue((livro.pasta / "caderno.lock").exists())
        livro.fechar()
        self.assertFalse((livro.pasta / "caderno.lock").exists())


class EsperaTests(unittest.TestCase):
    def test_grava_so_com_a_mudanca_e_o_cursor_parados(self) -> None:
        self.assertEqual(caderno.espera_restante(10.0, mudou_em=7.5, cursor_em=8.5), 0.0)
        self.assertAlmostEqual(caderno.espera_restante(10.0, mudou_em=7.5, cursor_em=9.5), 1.0)
        self.assertAlmostEqual(caderno.espera_restante(10.0, mudou_em=9.0, cursor_em=0.0), 1.5)


class AbreDoCadernoTests(unittest.TestCase):
    def estado(self, **campos: object) -> caderno.EstadoDaFolha:
        base: dict[str, object] = {"pagina": 0, "estado": caderno.LIDA, "motor": "auto", "modo_bloco": False}
        base.update(campos)
        return caderno.EstadoDaFolha(**base)  # type: ignore[arg-type]

    def test_o_mesmo_motor_abre_o_caderno(self) -> None:
        self.assertTrue(caderno.abre_do_caderno(self.estado(), motor="auto", modo_bloco=False))

    def test_motor_trocado_sem_correcao_le_de_novo(self) -> None:
        self.assertFalse(caderno.abre_do_caderno(self.estado(), motor="glifo", modo_bloco=False))
        self.assertFalse(caderno.abre_do_caderno(self.estado(), motor="auto", modo_bloco=True))

    def test_com_correcao_ou_conferida_abre_o_caderno_mesmo_com_outro_motor(self) -> None:
        self.assertTrue(caderno.abre_do_caderno(self.estado(correcoes=2, estado=caderno.EDITADA), motor="glifo", modo_bloco=False))
        self.assertTrue(caderno.abre_do_caderno(self.estado(estado=caderno.CONFERIDA), motor="glifo", modo_bloco=False))

    def test_a_pergunta_diz_o_tamanho_da_perda(self) -> None:
        self.assertEqual(
            caderno.frase_de_releitura(11, 7),
            "A folha 12 tem 7 correções. Ler de novo guarda esta versão como anterior e abre a leitura nova.",
        )
        self.assertIn("1 correção.", caderno.frase_de_releitura(0, 1))



def _com_diagrama(livro: str, folha: int) -> rico.DocumentoRico:
    from chess_diagram_ocr.text.pagina import BlocoDeDiagrama

    texto = BlocoDeTexto.de_linhas([LinhaLida(f"antes, folha {folha + 1}", (0.0, 0.0, 9.0, 9.0), 1.0, "camada")])  # type: ignore[arg-type]
    pagina = PaginaLida(
        documento=livro,
        pagina=folha,
        colunas=(Coluna(indice=0, blocos=(texto, BlocoDeDiagrama(indice=0, bbox=(10.0, 10.0, 60.0, 60.0)))),),
    )
    return rico.de_pagina(pagina)


class ExportarFolhasTests(unittest.TestCase):
    """S-614: o caderno inteiro num arquivo, com os exportadores de cada folha intactos."""

    def test_tres_folhas_em_ordem_com_as_imagens_de_cada_uma(self) -> None:
        from chess_diagram_ocr.text import exportacao

        folhas = [_com_diagrama("livro.pdf", 2), _doc(Path("livro.pdf"), 4, "só texto"), _com_diagrama("livro.pdf", 9)]
        recortes = {2: {1: Path("diagramas/x_f0003_d1.png")}, 9: {1: Path("diagramas/x_f0010_d1.png")}}
        relatorio = exportacao.exportar_folhas(
            folhas, exportacao.formato_de(".md"), titulo="livro.pdf — caderno", recortes=recortes, faltam=(0, 1, 3, 5, 6, 7, 8)
        )
        texto = relatorio.conteudo
        posicoes = [texto.index(f"# Folha {n}") for n in (3, 5, 10)]
        self.assertEqual(posicoes, sorted(posicoes), "as folhas saíram fora de ordem")
        self.assertEqual(texto.count("# Folha "), 3, "folha duplicada ou faltando")
        self.assertIn("x_f0003_d1.png", texto)
        self.assertIn("x_f0010_d1.png", texto)
        self.assertLess(texto.index("x_f0003_d1.png"), posicoes[1], "a imagem da folha 3 foi parar noutra folha")
        self.assertEqual(relatorio.diagramas, 2)
        self.assertIn("faltam as folhas 1-2, 4, 6-9", relatorio.avisos)

    def test_a_exportacao_de_uma_folha_nao_mudou(self) -> None:
        """`exportar` agora divide o laço com `exportar_folhas`; a saída de uma folha é a mesma."""
        from chess_diagram_ocr.text import exportacao

        doc = _com_diagrama("livro.pdf", 0)
        um = exportacao.exportar(doc, exportacao.formato_de(".txt"))
        self.assertTrue(um.conteudo.endswith("[Diagrama 1]\n"), um.conteudo)
        self.assertEqual(um.sem_recorte, 1)

    def test_intervalos(self) -> None:
        from chess_diagram_ocr.text.exportacao import intervalos

        self.assertEqual(intervalos([0, 1, 2, 3, 16]), "1-4, 17")
        self.assertEqual(intervalos([5]), "6")
        self.assertEqual(intervalos([]), "")


class IndiceDeFrasesTests(unittest.TestCase):
    def test_a_linha_diz_estado_correcoes_e_data(self) -> None:
        from chess_diagram_ocr.ui.texto_declarado import linha_do_indice

        self.assertEqual(
            linha_do_indice(11, caderno.CONFERIDA, 7, "2026-10-24T14:02:11"), "√ Folha 12 · conferida · 7 correções · 24/10 14:02"
        )
        self.assertEqual(linha_do_indice(0, caderno.EDITADA, 1, ""), "● Folha 1 · corrigida · 1 correção")
        self.assertEqual(linha_do_indice(2, caderno.LIDA, 0, ""), "○ Folha 3 · lida")

    def test_o_rodape_conta_as_conferidas_so_quando_ha(self) -> None:
        from chess_diagram_ocr.ui.texto_declarado import frase_do_rodape

        base = {"folha": 2, "trechos": 4, "diagramas": 0, "miniaturas": 0, "por_gravar": False, "do_caderno": True}
        self.assertIn("34 de 289 folhas conferidas", frase_do_rodape(**base, conferidas=(34, 289)))  # type: ignore[arg-type]
        self.assertNotIn("conferidas", frase_do_rodape(**base, conferidas=(0, 289)))  # type: ignore[arg-type]
        self.assertTrue(frase_do_rodape(**base).startswith("Folha 3 do caderno"))  # type: ignore[arg-type]



class PesquisavelLeOCadernoTests(_ComLivro):
    def test_o_cvoff_pega_so_as_folhas_corrigidas_pedidas_e_sem_travar(self) -> None:
        from chess_diagram_ocr.cli import texto_pesquisavel

        livro = caderno.abrir(self.livro)  # a janela que está corrigindo o livro
        assert livro is not None
        self.addCleanup(livro.fechar)
        livro.gravar(_doc(self.livro, 0, "só lida"))
        livro.gravar(_editado(_doc(self.livro, 1), " corrigida"), correcoes=1)
        livro.gravar(_editado(_doc(self.livro, 7), " fora do pedido"), correcoes=1)
        achadas = texto_pesquisavel._corrigidas_do_caderno(self.livro, [0, 1, 2])
        self.assertEqual(sorted(achadas), [1])
        self.assertIn("corrigida", achadas[1].para_texto())
        self.assertFalse(livro.somente_leitura, "o cvoff tomou a trava da janela")


if __name__ == "__main__":
    unittest.main()
