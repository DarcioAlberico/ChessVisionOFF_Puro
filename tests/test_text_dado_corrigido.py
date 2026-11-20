"""S-762: a correção volta como dado, e só pela porta da quarentena."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import numpy as np

from chess_diagram_ocr.cli import texto_correcoes
from chess_diagram_ocr.text import arquivo, coleta, correcao, dado_corrigido, dataset, ouro, rico
from chess_diagram_ocr.text import procedencia as pr
from chess_diagram_ocr.text.boxes import Caixa
from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida


def _linha(texto: str, y: float = 10.0, procedencia: str = "glifo") -> LinhaLida:
    # 10 pt por caractere que não é espaço, sem vão: o que importa é o centro de cada caixa cair na linha.
    return LinhaLida(texto=texto, bbox=(0.0, y, 400.0, y + 10.0), confianca=0.9, procedencia=procedencia)  # type: ignore[arg-type]


def _pagina(*linhas: LinhaLida, modelo: str = "ab12", documento: str = "livro.pdf") -> PaginaLida:
    bloco = BlocoDeTexto.de_linhas(linhas)
    return PaginaLida(
        documento=documento, pagina=3, largura=500.0, altura=700.0, colunas=(Coluna(blocos=(bloco,)),), modelo=modelo
    )


def _editado(pagina: PaginaLida, de: str, para: str) -> rico.DocumentoRico:
    doc = rico.de_pagina(pagina)
    corridas = []
    trocou = False
    for corrida in doc.corridas:
        if de in corrida.texto and not trocou:
            corridas.append(rico.Corrida(corrida.texto.replace(de, para, 1), corrida.atributos, corrida.faixa, bloco=corrida.bloco))
            trocou = True
        else:
            corridas.append(corrida)
    assert trocou, de
    return rico.DocumentoRico(corridas=tuple(corridas), origem=doc.origem)


class ParesTocadosTests(unittest.TestCase):
    def test_so_a_palavra_tocada_vira_par(self) -> None:
        """É a crítica ao carimbo do bloco: `humano` cobre o parágrafo, e o par não."""
        doc = _editado(_pagina(_linha("the wbite rook wiil move")), "wbite", "white")
        pares = dado_corrigido.pares_tocados(doc)
        self.assertEqual([(p.antes, p.depois) for p in pares], [("wbite", "white")])
        # `wiil` está errado, e ninguém o tocou: não é par, ainda que o bloco saia carimbado.
        carimbado = correcao.com_procedencia_humana(doc)
        self.assertTrue(any(c.procedencia == "humano" and "wiil" in c.texto for c in carimbado.corridas))
        self.assertEqual([p.antes for p in dado_corrigido.pares_tocados(carimbado)], ["wbite"])

    def test_a_procedencia_leva_o_motor_e_o_modelo(self) -> None:
        doc = _editado(_pagina(_linha("the wbite rook")), "wbite", "white")
        self.assertEqual(dado_corrigido.pares_tocados(doc)[0].procedencia, "corrigido_de:glifo@ab12")

    def test_sem_modelo_e_dito(self) -> None:
        doc = _editado(_pagina(_linha("the wbite rook"), modelo=""), "wbite", "white")
        self.assertEqual(dado_corrigido.pares_tocados(doc)[0].procedencia, "corrigido_de:glifo@desconhecido")

    def test_partir_e_juntar_nao_tem_par(self) -> None:
        doc = _editado(_pagina(_linha("say ofthe rook")), "ofthe", "of the")
        self.assertEqual(dado_corrigido.pares_tocados(doc), ())

    def test_a_camada_nao_errou(self) -> None:
        doc = _editado(_pagina(_linha("the wbite rook", procedencia="camada")), "wbite", "white")
        self.assertEqual(dado_corrigido.pares_tocados(doc), ())

    def test_folha_sem_edicao(self) -> None:
        self.assertEqual(dado_corrigido.pares_tocados(rico.de_pagina(_pagina(_linha("the wbite rook")))), ())


class NaoMedeTests(unittest.TestCase):
    """A saída do item: nenhuma correção chega a teste."""

    def test_o_registro_corrigido_nao_mede(self) -> None:
        self.assertFalse(pr.Registro(procedencia=pr.corrigido_de("glifo", "ab12")).mede)

    def test_a_porta_da_verdade_recusa(self) -> None:
        for valor in (pr.corrigido_de("glifo", "ab12"), pr.corrigido_de("tesseract"), pr.MODELO, pr.DESCONHECIDA):
            with self.subTest(valor), self.assertRaises(pr.VerdadeContaminada):
                pr.exigir_verdade(valor, onde="scan-ouro")
        pr.exigir_verdade(pr.HUMANO, onde="scan-ouro")

    def test_o_cvtxt_corrigido_nao_e_verdade_cega(self) -> None:
        """O scan-ouro (S-703) não aceita folha com leitura de motor por trás, corrigida ou não."""
        doc = _editado(_pagina(_linha("the wbite rook")), "wbite", "white")
        for documento in (doc, correcao.com_procedencia_humana(doc), rico.de_pagina(_pagina(_linha("nada tocado")))):
            with self.assertRaises(dado_corrigido.FolhaAncorada):
                dado_corrigido.exigir_documento_cego(documento, onde="scan-ouro")
        dado_corrigido.exigir_documento_cego(rico.DocumentoRico(corridas=(), origem=None), onde="scan-ouro")

    def test_no_split_ele_conta_como_modelo_e_o_audit_reprova(self) -> None:
        registro = {"a": pr.Registro(procedencia=pr.corrigido_de("glifo", "ab12")), "b": pr.Registro(procedencia=pr.HUMANO)}
        self.assertEqual(dataset.procedencia_de("a", registro), pr.MODELO)
        codigos = dataset.codigos_de_procedencia(np.array(["a", "b"]), registro)
        self.assertEqual(codigos.tolist(), [pr.CODIGO[pr.MODELO], pr.CODIGO[pr.HUMANO]])
        self.assertFalse(int(codigos[0]) >= pr.CODIGO[pr.HUMANO])
        relatorio = {"procedencia_por_lado": {"teste": {pr.MODELO: 1}}}
        self.assertTrue(any("modelo" in v for v in pr.violacoes_do_split(relatorio)))

    def test_o_csv_aceita_o_corrigido_e_recusa_o_resto(self) -> None:
        with TemporaryDirectory() as raiz:
            csv = Path(raiz) / "p.csv"
            csv.write_text("uuid,livro,pagina,procedencia,rotulado_em\na,L,1,corrigido_de:glifo@ab12,\n", encoding="utf-8")
            self.assertEqual(pr.ler(csv)["a"].procedencia, "corrigido_de:glifo@ab12")
            self.assertIn("1 modelo", pr.resumo(pr.ler(csv)))
            csv.write_text("uuid,livro,pagina,procedencia,rotulado_em\na,L,1,corrigido_de:glifo,\n", encoding="utf-8")
            with self.assertRaises(pr.ArquivoInvalido):
                pr.ler(csv)


def _manifesto(identidade: str, split: str, *, fora_do_treino: bool = False) -> ouro.Manifesto:
    livro = ouro.LivroDoOuro(identidade=identidade, split=split, lingua="eng", fora_do_treino=fora_do_treino)
    return ouro.Manifesto(versao=1, congelado_em="2026-10-30", primeira_leitura_do_teste=None, livros=(livro,), folhas=())


class LivroDoTesteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pdf = Path(self.tmp.name) / "livro.pdf"
        self.pdf.write_bytes(b"%PDF-1.4 qualquer coisa")
        self.identidade = ouro.identidade_de(self.pdf)

    def test_o_livro_do_teste_nunca_entra(self) -> None:
        manifesto = _manifesto(self.identidade or "", ouro.TESTE)
        self.assertEqual(dado_corrigido.livro_recusado(self.pdf, manifesto), "livro do teste")
        doc = _editado(_pagina(_linha("the wbite rook")), "wbite", "white")
        imagem = np.full((700, 500, 3), 255, np.uint8)
        with mock.patch("chess_diagram_ocr.text.leitor.segmentar") as segmentar:
            recortes, envio = dado_corrigido.preparar(doc, self.pdf, imagem, dpi=72, manifesto=manifesto)
        self.assertEqual(recortes, [])
        self.assertEqual(envio.recusado, "livro do teste")
        segmentar.assert_not_called()

    def test_o_que_o_manifesto_tira_do_treino_tambem_nao(self) -> None:
        manifesto = _manifesto(self.identidade or "", ouro.RESERVA, fora_do_treino=True)
        self.assertTrue(dado_corrigido.livro_recusado(self.pdf, manifesto))

    def test_o_livro_do_dev_e_o_de_fora_entram(self) -> None:
        self.assertEqual(dado_corrigido.livro_recusado(self.pdf, _manifesto(self.identidade or "", ouro.DEV)), "")
        self.assertEqual(dado_corrigido.livro_recusado(self.pdf, _manifesto("outro", ouro.TESTE)), "")

    def test_sem_identidade_nao_entra(self) -> None:
        self.assertTrue(dado_corrigido.livro_recusado(Path(self.tmp.name) / "nao_existe.pdf", _manifesto("x", ouro.DEV)))


class SerieForaDoManifestoTests(unittest.TestCase):
    """O volume seguinte de uma série do teste não está no manifesto, e não entra na quarentena (S-750)."""

    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vazio = _manifesto("outro", ouro.DEV)

    def _pdf(self, nome: str, conteudo: bytes = b"%PDF-1.4 volume") -> Path:
        pdf = Path(self.tmp.name) / nome
        pdf.write_bytes(conteudo)
        return pdf

    def test_o_volume_quatro_pelo_resumo_da_lista_versionada(self) -> None:
        """`58529adc...` é o volume 4 de uma série que tem o 2 no teste, e não está no manifesto."""
        pdf = self._pdf("qualquer.pdf")
        with mock.patch.object(dado_corrigido, "identidade_de", return_value="58529adc955cc4ea"):
            self.assertTrue(dado_corrigido.livro_recusado(pdf, self.vazio))

    def test_a_lista_versionada_so_tem_resumo(self) -> None:
        import re

        exclusao = ouro.carregar_exclusao()
        self.assertTrue(exclusao.identidades and exclusao.series)
        for valor in (*exclusao.identidades, *exclusao.series):
            self.assertRegex(valor, re.compile(r"^[0-9a-f]{16}$"))
        bruto = (ouro.BUNDLE_ROOT / ouro.CAMINHO_DA_EXCLUSAO).read_text(encoding="utf-8")
        self.assertEqual(set(json.loads(bruto)), {"versao", "item", "gerada_em", "nota", "identidades", "series"})

    def test_cada_livro_do_teste_tem_a_sua_serie(self) -> None:
        """Não confere qual, porque o nome não está aqui; confere que nenhum ficou de fora em número."""
        manifesto = ouro.carregar()
        self.assertGreaterEqual(len(ouro.carregar_exclusao().series), len([x for x in manifesto.livros if x.split == ouro.TESTE]) - 1)

    def test_a_chave_ignora_numero_ano_e_pontuacao(self) -> None:
        self.assertEqual(ouro.chave_de_serie("Autor X - Titulo Y 2 (2019)"), ouro.chave_de_serie("Autor X - Titulo Y 5 (2024)"))
        self.assertEqual(ouro.chave_de_serie("Autor X - Titulo Y vol. 3"), ouro.chave_de_serie("autor x título y"))
        self.assertNotEqual(ouro.chave_de_serie("Autor X - Titulo Y"), ouro.chave_de_serie("Autor X - Titulo Z"))

    def test_o_volume_que_ainda_nao_chegou_cai_pelo_nome(self) -> None:
        serie = ouro.chave_de_serie("Autor X - Titulo Y 2 (2019)")
        exclusao = ouro.Exclusao(series=frozenset({serie}))
        pdf = self._pdf("Autor X - Titulo Y 7 (2030).pdf")
        self.assertTrue(dado_corrigido.livro_recusado(pdf, self.vazio, exclusao))
        self.assertEqual(dado_corrigido.livro_recusado(self._pdf("Outro Livro.pdf"), self.vazio, exclusao), "")

    def test_preparar_recusa_antes_da_imagem(self) -> None:
        doc = _editado(_pagina(_linha("the wbite rook")), "wbite", "white")
        with (
            mock.patch.object(dado_corrigido, "identidade_de", return_value="58529adc955cc4ea"),
            mock.patch("chess_diagram_ocr.text.leitor.segmentar") as segmentar,
        ):
            recortes, envio = dado_corrigido.preparar(doc, self._pdf("x.pdf"), np.zeros((10, 10, 3), np.uint8), dpi=72, manifesto=self.vazio)
        self.assertEqual(recortes, [])
        self.assertTrue(envio.recusado)
        segmentar.assert_not_called()


def _caixas_da_linha(texto: str, y: float = 10.0) -> list[Caixa]:
    """Uma caixa por letra, em pixels a 72 dpi: 10 px de largura cada, em ordem."""
    letras = len("".join(texto.split()))
    return [Caixa(10 * k, int(y) + 1, 10 * k + 8, int(y) + 9) for k in range(letras)]


class RecortesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cinza = np.zeros((700, 500), np.uint8)
        for k in range(40):
            self.cinza[11:19, 10 * k : 10 * k + 8] = k + 100

    def _par(self, de: str, para: str, *linhas: LinhaLida) -> tuple[dado_corrigido.ParTocado, PaginaLida]:
        pagina = _pagina(*linhas)
        return (dado_corrigido.pares_tocados(_editado(pagina, de, para))[0], pagina)

    def test_so_a_letra_que_mudou_e_a_tinta_dela(self) -> None:
        par, pagina = self._par("wbite", "white", _linha("the wbite rook"))
        saida = dado_corrigido.recortes_do_par(par, pagina, self.cinza, _caixas_da_linha("the wbite rook"), escala_px=1.0)
        self.assertEqual([r.palpite for r in saida], ["h"])
        # `the` são 3 caixas, `w` a quarta, e o `b` errado a quinta: índice 4.
        self.assertEqual(int(saida[0].imagem[16, 16]), 104)
        self.assertEqual(saida[0].imagem.shape, (coleta.LADO, coleta.LADO))
        self.assertEqual(saida[0].procedencia, "corrigido_de:glifo@ab12")
        self.assertEqual((saida[0].antes, saida[0].depois), ("wbite", "white"))

    def test_a_conta_que_nao_fecha_nao_adivinha(self) -> None:
        par, pagina = self._par("wbite", "white", _linha("the wbite rook"))
        caixas = _caixas_da_linha("the wbite rook")[:-1]
        self.assertEqual(dado_corrigido.recortes_do_par(par, pagina, self.cinza, caixas, escala_px=1.0), [])

    def test_tamanho_diferente_nao_tem_recorte(self) -> None:
        par, pagina = self._par("fi1rst", "first", _linha("the fi1rst rook"))
        caixas = _caixas_da_linha("the fi1rst rook")
        self.assertEqual(dado_corrigido.recortes_do_par(par, pagina, self.cinza, caixas, escala_px=1.0), [])

    def test_a_palavra_da_segunda_linha(self) -> None:
        par, pagina = self._par("wbite", "white", _linha("a rook", 10.0), _linha("the wbite", 30.0))
        caixas = [*_caixas_da_linha("a rook", 10.0), *_caixas_da_linha("the wbite", 30.0)]
        self.cinza[31:39, 40:48] = 77
        saida = dado_corrigido.recortes_do_par(par, pagina, self.cinza, caixas, escala_px=1.0)
        self.assertEqual([r.palpite for r in saida], ["h"])
        self.assertEqual(int(saida[0].imagem[16, 16]), 77)


class QuarentenaTests(unittest.TestCase):
    """O caminho inteiro: da correção ao registro, sem passar pela base."""

    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.quarentena = self.raiz / "revisao_ocr"

    def _recorte(self, valor: int = 40) -> coleta.Recorte:
        rng = np.random.default_rng(valor)
        return coleta.Recorte(
            rng.integers(0, 255, (coleta.LADO, coleta.LADO), dtype=np.uint8),
            "h",
            0.0,
            livro="Livro",
            pagina=3,
            procedencia="corrigido_de:glifo@ab12",
            antes="wbite",
            depois="white",
        )

    def test_a_coleta_nao_conhece_a_base_e_o_csv_guarda_o_par(self) -> None:
        recorte = self._recorte()
        relatorio = dado_corrigido.enviar([recorte], self.quarentena)
        self.assertEqual(relatorio.gravados, 1)
        self.assertEqual(len(list((self.quarentena / recorte.pasta).glob("*.png"))), 1)
        linha = coleta._ler_corrigidos(self.quarentena)[recorte.uuid]
        self.assertEqual((linha["procedencia"], linha["antes"], linha["depois"]), ("corrigido_de:glifo@ab12", "wbite", "white"))
        self.assertFalse((self.raiz / "training_data").exists())

    def test_promover_nao_lava_a_origem(self) -> None:
        """A mão que confirma a pasta não apaga a leitura por trás: entra no treino, e não mede."""
        recorte = self._recorte()
        dado_corrigido.enviar([recorte], self.quarentena)
        comum = coleta.Recorte(
            np.random.default_rng(1).integers(0, 255, (coleta.LADO, coleta.LADO), dtype=np.uint8), "e", 0.2, livro="Livro", pagina=9
        )
        coleta.coletar([comum], self.quarentena)
        base = self.raiz / "base"
        csv = self.raiz / "procedencia.csv"
        feita = coleta.promover(self.quarentena, base, registro=csv, quando="2026-11-06")
        self.assertEqual(len(feita.promovidos), 2)
        registro = pr.ler(csv)
        self.assertEqual(registro[recorte.uuid].procedencia, "corrigido_de:glifo@ab12")
        self.assertFalse(registro[recorte.uuid].mede)
        self.assertEqual(registro[comum.uuid].procedencia, pr.HUMANO)

    def test_a_segunda_coleta_nao_apaga_a_primeira(self) -> None:
        um, dois = self._recorte(1), self._recorte(2)
        dado_corrigido.enviar([um], self.quarentena)
        dado_corrigido.enviar([dois], self.quarentena)
        self.assertEqual(set(coleta._ler_corrigidos(self.quarentena)), {um.uuid, dois.uuid})

    def test_o_csv_da_raiz_nao_vira_classe(self) -> None:
        dado_corrigido.enviar([self._recorte()], self.quarentena)
        self.assertEqual(coleta.promover(self.quarentena).pastas_indecifraveis, ())

    def test_o_comando_leva_o_cvtxt_a_quarentena(self) -> None:
        """`cvoff-texto-correcoes --quarentena`: da folha gravada até o recorte, e o livro fora do manifesto entra."""
        pdf = self.raiz / "livro.pdf"
        pdf.write_bytes(b"%PDF-1.4 qualquer coisa")
        pagina = _pagina(_linha("the wbite rook"), documento=str(pdf))
        doc = correcao.com_procedencia_humana(_editado(pagina, "wbite", "white"))
        cvtxt = self.raiz / "folha.cvtxt"
        arquivo.gravar(cvtxt, doc)
        imagem = np.full((700, 500, 3), 255, np.uint8)
        imagem[11:19, 40:48] = 0
        caixas = _caixas_da_linha("the wbite rook")
        with (
            mock.patch("chess_diagram_ocr.pdf_io.render_pdf_page", return_value=imagem),
            mock.patch("chess_diagram_ocr.text.leitor.segmentar", return_value=(imagem[:, :, 0], imagem[:, :, 0], 10, caixas, [])),
            mock.patch.object(ouro, "carregar", return_value=_manifesto("outro", ouro.TESTE)),
        ):
            enviado = texto_correcoes.para_quarentena([cvtxt], self.quarentena, dpi=72)
        self.assertEqual((enviado["pares"], enviado["gravados"], enviado["sem_recorte"]), (1, 1, 0))
        self.assertEqual(enviado["procedencias"], {"corrigido_de:glifo@ab12": 1})
        self.assertEqual(len(list(self.quarentena.rglob("*.png"))), 1)
        json.dumps(enviado)


class ModeloNaPaginaTests(unittest.TestCase):
    def test_ida_e_volta_sem_subir_o_esquema(self) -> None:
        pagina = _pagina(_linha("the rook"), modelo="ab12")
        dados = pagina.para_json()
        self.assertEqual(dados["esquema"], 1)
        self.assertEqual(PaginaLida.de_json(dados).modelo, "ab12")

    def test_sem_modelo_o_arquivo_e_o_de_antes(self) -> None:
        dados = _pagina(_linha("the rook"), modelo="").para_json()
        self.assertNotIn("modelo", dados)
        self.assertEqual(PaginaLida.de_json(dados).modelo, "")

    def test_o_leitor_diz_quem_leu(self) -> None:
        from types import SimpleNamespace

        from chess_diagram_ocr.text import leitor

        falso = SimpleNamespace(classifier=SimpleNamespace(meta=SimpleNamespace(modelo_sha256="cd34")))
        self.assertEqual(leitor._sha_do_modelo(falso), "cd34")
        self.assertEqual(leitor._sha_do_modelo(SimpleNamespace()), "")


if __name__ == "__main__":
    unittest.main()
