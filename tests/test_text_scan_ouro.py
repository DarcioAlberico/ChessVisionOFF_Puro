"""O scan-ouro (S-703): o manifesto, a verdade às cegas, o acordo da dupla digitação e o relógio. Sem PDF nem motor: o que se testa é a regra."""

from __future__ import annotations

import ast
import contextlib
import io
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import numpy as np
from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr.cli import texto_prosa
from chess_diagram_ocr.text import dado_corrigido, ouro, prata, procedencia, regua_prosa, scan_ouro
from chess_diagram_ocr.text import transcricao_scan as ts
from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida
from chess_diagram_ocr.text.rico import DocumentoRico

RAIZ = Path(__file__).resolve().parents[1]
_SHA_A = "a" * 16
_SHA_B = "b" * 16


def _pagina(motor: str) -> PaginaLida:
    bloco = BlocoDeTexto.de_linhas([LinhaLida("the rook", (0.0, 0.0, 9.0, 9.0), 0.5, motor)])  # type: ignore[arg-type]
    return PaginaLida(pagina=0, colunas=(Coluna(indice=0, blocos=(bloco,)),))


def _doc_cego() -> DocumentoRico:
    return ts.documento_da_partida((), (), ts.VAZIO, indice=0)


def _registro(identidade: str = "aaaa", folha: int = 1, passada: int = 1, linhas: tuple[str, ...] = ("uma linha",), **campos) -> ts.FolhaDaPassada:
    return ts.FolhaDaPassada(
        identidade=identidade, folha=folha, passada=passada, procedencia=procedencia.transcricao(passada), linhas=linhas,
        partida=campos.pop("partida", ts.VAZIO), sha_imagem=campos.pop("sha_imagem", _SHA_A), sha_folha=campos.pop("sha_folha", _SHA_B),
        segundos=campos.pop("segundos", 60.0), completa=campos.pop("completa", True), **campos,
    )


def _manifesto(*folhas: scan_ouro.FolhaDoScanOuro) -> scan_ouro.ScanOuro:
    livros = {f.identidade: scan_ouro.LivroDoScanOuro(f.identidade, f.split, f.lingua, f.producao) for f in folhas}
    return scan_ouro.ScanOuro(scan_ouro.VERSAO, "2026-11-06", None, tuple(livros.values()), folhas)


def _folha(identidade: str = "aaaa", folha: int = 1, *, dupla: bool = False) -> scan_ouro.FolhaDoScanOuro:
    return scan_ouro.FolhaDoScanOuro(identidade, folha, "eng", prata.ATE_150, ouro.MISTO, scan_ouro.DEV, dupla, _SHA_B)


class ManifestoVersionadoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.m = scan_ouro.carregar(RAIZ / scan_ouro.CAMINHO)

    def test_o_manifesto_cumpre_a_entrega(self) -> None:
        self.assertEqual([], scan_ouro.problemas(self.m))
        self.assertGreaterEqual(len(self.m.folhas), 30)
        self.assertGreaterEqual(len({f.identidade for f in self.m.folhas}), 8)
        self.assertGreaterEqual(len({f.lingua for f in self.m.folhas}), 5)
        self.assertEqual(set(prata.ESTRATOS), {f.producao for f in self.m.folhas})

    def test_o_manifesto_so_tem_identidades(self) -> None:
        """O repositório é público: nem nome de arquivo, nem caminho, nem texto de livro."""
        for livro in self.m.livros:
            self.assertRegex(livro.identidade, r"^[0-9a-f]{16}$")
        cru = (RAIZ / scan_ouro.CAMINHO).read_text(encoding="utf-8")
        self.assertNotIn(".pdf", cru)
        self.assertNotIn("texto", json.loads(cru)["folhas"][0])

    def test_o_teste_nao_foi_lido(self) -> None:
        self.assertIsNone(self.m.primeira_leitura_do_teste)

    def test_nenhum_livro_esta_tambem_no_ouro(self) -> None:
        no_ouro = {livro.identidade for livro in ouro.carregar().livros}
        self.assertEqual(set(), no_ouro & {livro.identidade for livro in self.m.livros})

    def test_o_sorteio_de_folhas_e_o_do_ouro(self) -> None:
        """Duas contas fixas, porque a ordem do sorteio é parte do contrato: mudá-la muda o que se digitou."""
        self.assertEqual(sorted(ouro.ordem_das_folhas("abc", 100)), list(range(9, 93)))
        semente = self.m.sorteio["semente"]
        self.assertEqual(ouro.ordem_dos_livros(["a", "b", "c"], semente), ouro.ordem_dos_livros(["c", "b", "a"], semente))

    def test_a_escolha_nao_importa_leitor_nenhum(self) -> None:
        """Nem glifo, nem Tesseract, nem fusão, nem rapidocr: é o critério do item, e a régua não pode ver quem ela mede."""
        proibidos = {"recognizer", "tesseract", "fusao", "leitor_de_linha", "modelo", "rapidocr", "classifier", "motor"}
        for caminho in (
            RAIZ / "docs/metrics/texto_scan_ouro_2026-11-06/sortear.py",
            RAIZ / "src/chess_diagram_ocr/text/scan_ouro.py",
            RAIZ / "src/chess_diagram_ocr/text/transcricao_scan.py",
        ):
            nomes: set[str] = set()
            for no in ast.walk(ast.parse(caminho.read_text(encoding="utf-8"))):
                if isinstance(no, ast.Import):
                    nomes.update(a.name.rsplit(".", 1)[-1] for a in no.names)
                elif isinstance(no, ast.ImportFrom):
                    nomes.update((no.module or "").split("."))
                    nomes.update(a.name for a in no.names)
            self.assertEqual(set(), nomes & proibidos, caminho.name)


class ProblemasTests(unittest.TestCase):
    """Cada regra reprova: guarda que nunca acusou não é guarda."""

    def setUp(self) -> None:
        self.m = scan_ouro.carregar(RAIZ / scan_ouro.CAMINHO)

    def _acusa(self, trecho: str, manifesto: scan_ouro.ScanOuro) -> None:
        erros = scan_ouro.problemas(manifesto)
        self.assertTrue(any(trecho in e for e in erros), erros)

    def test_poucas_folhas_e_poucos_livros(self) -> None:
        self._acusa("folhas, e o mínimo", replace(self.m, folhas=self.m.folhas[:-1]))
        self._acusa("livros, e o mínimo", replace(self.m, livros=self.m.livros[:3], folhas=self.m.folhas[:9]))

    def test_livro_nos_dois_splits(self) -> None:
        self._acusa("repetido", replace(self.m, livros=(*self.m.livros, replace(self.m.livros[0], split=scan_ouro.TESTE))))

    def test_livro_visto_no_teste(self) -> None:
        livros = tuple(replace(x, visto=True) if x.split == scan_ouro.TESTE else x for x in self.m.livros)
        self._acusa("já foi visto", replace(self.m, livros=livros))

    def test_grupo_nos_dois_splits(self) -> None:
        dev = next(x for x in self.m.livros if x.split == scan_ouro.DEV)
        teste = next(x for x in self.m.livros if x.split == scan_ouro.TESTE)
        livros = tuple(replace(x, grupo="mesma") if x in (dev, teste) else x for x in self.m.livros)
        self._acusa("grupo", replace(self.m, livros=livros))

    def test_menos_de_metade_no_misto_conta_o_a_conferir_contra(self) -> None:
        folhas = tuple(replace(f, conteudo=scan_ouro.A_CONFERIR) if f.conteudo == ouro.MISTO else f for f in self.m.folhas)
        self._acusa("misto", replace(self.m, folhas=folhas))

    def test_menos_de_um_terco_ate_150(self) -> None:
        folhas = tuple(replace(f, producao=prata.DE_300) for f in self.m.folhas)
        self._acusa("um terço", replace(self.m, folhas=folhas))

    def test_dupla_digitacao_de_menos(self) -> None:
        folhas = tuple(replace(f, dupla=False) for f in self.m.folhas)
        self._acusa("dupla digitação", replace(self.m, folhas=folhas))

    def test_sem_seculo_xix(self) -> None:
        self._acusa("século XIX", replace(self.m, livros=tuple(replace(x, seculo_xix=False) for x in self.m.livros)))

    def test_folha_sem_sha(self) -> None:
        self._acusa("sem o sha", replace(self.m, folhas=(replace(self.m.folhas[0], sha_folha=""), *self.m.folhas[1:])))

    def test_leitura_do_teste_antes_de_congelar(self) -> None:
        self._acusa("antes de congelar", replace(self.m, primeira_leitura_do_teste="2026-01-01"))

    def test_gravar_e_carregar_dao_o_mesmo(self) -> None:
        destino = pasta_temporaria(self) / "m.json"
        scan_ouro.gravar(self.m, destino)
        self.assertEqual(self.m, scan_ouro.carregar(destino))
        self.assertNotIn(b"\r", destino.read_bytes())

    def test_a_primeira_leitura_nao_se_sobrescreve(self) -> None:
        lido = scan_ouro.registrar_leitura_do_teste(self.m, "2026-12-01")
        self.assertEqual("2026-12-01", lido.primeira_leitura_do_teste)
        self.assertEqual("2026-12-01", scan_ouro.registrar_leitura_do_teste(lido, "2027-01-01").primeira_leitura_do_teste)


class ProcedenciaTests(unittest.TestCase):
    def test_transcricao_mede_e_e_humana(self) -> None:
        valor = procedencia.transcricao(2)
        self.assertEqual("transcricao:2", valor)
        self.assertEqual(procedencia.HUMANO, procedencia.classe(valor))
        procedencia.exigir_verdade(valor, onde="teste")
        self.assertTrue(procedencia.Registro(procedencia=valor).mede)

    def test_o_scan_ouro_recusa_humano_e_corrigido(self) -> None:
        procedencia.exigir_transcricao(procedencia.transcricao(1), onde="scan-ouro")
        for valor in (procedencia.HUMANO, procedencia.corrigido_de("glifo", "ab"), procedencia.MODELO, "transcricao:", "transcricao:x"):
            with self.subTest(valor=valor), self.assertRaises(procedencia.VerdadeContaminada):
                procedencia.exigir_transcricao(valor, onde="scan-ouro")


class CadernoDaPassadaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)
        self.backup = pasta_temporaria(self)
        ts.declarar_backup(self.pasta, self.backup)

    def test_a_segunda_passada_nao_ve_a_primeira(self) -> None:
        primeira = ts.CadernoDaPassada(self.pasta, 1)
        primeira.gravar(_registro(linhas=("digitada na primeira",)), _doc_cego())
        segunda = ts.CadernoDaPassada(self.pasta, 2)
        self.assertIsNone(segunda.ler("aaaa", 1))
        self.assertEqual(set(), segunda.concluidas())
        self.assertEqual(("digitada na primeira",), primeira.ler("aaaa", 1).linhas)

    def test_o_jsonl_tem_os_dois_shas_e_a_procedencia(self) -> None:
        ts.CadernoDaPassada(self.pasta, 1).gravar(_registro(), _doc_cego())
        dados = json.loads(ts.caminho_da_passada(self.pasta, 1).read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual((_SHA_A, _SHA_B, "transcricao:1"), (dados["sha_imagem"], dados["sha_folha"], dados["procedencia"]))

    def test_a_ultima_gravacao_da_folha_vale(self) -> None:
        caderno = ts.CadernoDaPassada(self.pasta, 1)
        caderno.gravar(_registro(linhas=("velha",), completa=False), _doc_cego())
        caderno.gravar(_registro(linhas=("nova",)), _doc_cego())
        self.assertEqual(("nova",), caderno.ler("aaaa", 1).linhas)

    def test_folha_escrita_sobre_um_motor_nao_grava(self) -> None:
        """A porta da S-762. A procedência `tesseract` só existe na página depois da S-722; até lá a fusão sai `glifo`. Nada chega ao arquivo."""
        caderno = ts.CadernoDaPassada(self.pasta, 1)
        for motor in ("glifo", "rapidocr"):
            doc = DocumentoRico(corridas=(), origem=_pagina(motor))
            with self.subTest(motor=motor), self.assertRaises(dado_corrigido.FolhaAncorada):
                caderno.gravar(_registro(), doc)
        self.assertFalse(caderno.arquivo.exists())

    def test_procedencia_que_nao_e_transcricao_nao_grava(self) -> None:
        caderno = ts.CadernoDaPassada(self.pasta, 1)
        for valor in (procedencia.HUMANO, procedencia.corrigido_de("glifo", "ab")):
            with self.subTest(valor=valor), self.assertRaises(procedencia.VerdadeContaminada):
                caderno.gravar(replace(_registro(), procedencia=valor), _doc_cego())
        self.assertFalse(caderno.arquivo.exists())

    def test_a_camada_de_terceiro_passa(self) -> None:
        caixas = ((0.0, 0.0, 100.0, 20.0),)
        doc = ts.documento_da_partida(("da camada",), caixas, ts.CAMADA, indice=3)
        self.assertEqual({"camada"}, set(doc.origem.procedencias()))
        ts.CadernoDaPassada(self.pasta, 1).gravar(_registro(partida=ts.CAMADA), doc)

    def test_a_segunda_passada_so_parte_do_vazio(self) -> None:
        """As duas partindo da mesma camada concordariam nos erros que ninguém viu."""
        self.assertEqual((ts.VAZIO,), ts.partidas_da_passada(2))
        with self.assertRaises(ValueError):
            ts.CadernoDaPassada(self.pasta, 2).gravar(_registro(passada=2, partida=ts.CAMADA), _doc_cego())

    def test_o_registro_de_outra_passada_nao_entra(self) -> None:
        with self.assertRaises(ValueError):
            ts.CadernoDaPassada(self.pasta, 2).gravar(_registro(passada=1), _doc_cego())

    def test_pasta_dentro_de_repositorio_e_recusada(self) -> None:
        with self.assertRaises(ts.PastaNoRepositorio):
            ts.CadernoDaPassada(RAIZ / "data" / "transcricao", 1)
        with self.assertRaises(ts.PastaNoRepositorio):
            ts.declarar_backup(self.pasta, RAIZ / "data" / "copia")

    def test_sem_backup_declarado_nada_grava(self) -> None:
        outra = pasta_temporaria(self)
        with self.assertRaises(ts.SemBackup):
            ts.CadernoDaPassada(outra, 1).gravar(_registro(), _doc_cego())
        self.assertFalse(ts.caminho_da_passada(outra, 1).exists())

    def test_o_backup_e_a_propria_pasta_nao_vale(self) -> None:
        with self.assertRaises(ts.SemBackup):
            ts.declarar_backup(self.pasta, self.pasta)

    def test_cada_gravacao_chega_ao_backup(self) -> None:
        self.assertEqual("em_dia", ts.estado_do_backup(self.pasta))
        self.assertTrue(ts.CadernoDaPassada(self.pasta, 1).gravar(_registro(), _doc_cego()))
        self.assertEqual(
            ts.caminho_da_passada(self.pasta, 1).read_bytes(), ts.caminho_da_passada(self.backup, 1).read_bytes(),
        )
        self.assertEqual("em_dia", ts.estado_do_backup(self.pasta))

    def test_backup_que_falha_nao_perde_a_folha_e_avisa(self) -> None:
        caderno = ts.CadernoDaPassada(self.pasta, 1)
        with mock.patch.object(ts.shutil, "copyfile", side_effect=OSError("disco cheio")):
            self.assertFalse(caderno.gravar(_registro(), _doc_cego()))
        self.assertIsNotNone(caderno.ler("aaaa", 1))
        self.assertEqual("atrasado", ts.estado_do_backup(self.pasta))


class LinhasDaFolhaTests(unittest.TestCase):
    def test_a_camada_vai_a_linha_que_contem_a_palavra(self) -> None:
        caixas = [(0.0, 0.0, 400.0, 30.0), (0.0, 40.0, 400.0, 70.0)]
        escala = 72.0 / ts.DPI
        def palavra(x: float, y: float, texto: str) -> tuple[float, float, float, float, str, int, int, int]:
            return (x * escala, y * escala, (x + 40) * escala, (y + 20) * escala, texto, 0, 0, 0)
        palavras = [palavra(100, 45, "direita"), palavra(0, 45, "esquerda"), palavra(0, 5, "cima"), palavra(0, 200, "fora")]
        self.assertEqual(["cima", "esquerda direita"], ts.textos_da_camada(palavras, caixas))

    def test_o_recorte_tem_folga_e_nao_passa_da_folha(self) -> None:
        imagem = np.zeros((100, 200, 3), np.uint8)
        self.assertEqual((18, 58), ts.recorte_da_linha(imagem, (10.0, 10.0, 60.0, 20.0)).shape[:2])
        self.assertEqual((14, 44), ts.recorte_da_linha(imagem, (0.0, 0.0, 40.0, 10.0)).shape[:2])

    def test_a_geometria_nao_chama_classificador(self) -> None:
        """Com uma folha desenhada: acha as linhas, e nenhum reconhecedor é construído."""
        import cv2

        imagem = np.full((400, 800, 3), 255, np.uint8)
        # Frases diferentes: os vãos alinhados de uma frase repetida são calha de coluna, e com razão.
        for y, frase in ((80, "linha de prosa aqui"), (160, "outra frase bem mais comprida"), (240, "e uma terceira para fechar a conta")):
            cv2.putText(imagem, frase, (40, y), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
        with mock.patch("chess_diagram_ocr.text.recognizer.build_glyph_recognizer", side_effect=AssertionError("leu")):
            caixas = ts.linhas_da_folha(imagem, ())
        self.assertEqual(3, len(caixas))
        self.assertLess(caixas[0][1], caixas[1][1])


class RelogioTests(unittest.TestCase):
    def test_soma_entre_teclas(self) -> None:
        r = ts.Relogio(100.0)
        r.atividade(130.0)
        r.atividade(190.0)
        self.assertEqual(90.0, r.segundos(190.0))

    def test_a_pausa_longa_conta_so_o_teto(self) -> None:
        r = ts.Relogio(0.0)
        r.atividade(10.0)
        r.atividade(10_000.0)
        self.assertEqual(10.0 + ts.OCIOSO_MAXIMO, r.segundos(10_000.0))

    def test_continua_de_onde_parou(self) -> None:
        self.assertEqual(70.0, ts.Relogio(0.0, inicial=60.0).segundos(10.0))

    def test_por_extenso(self) -> None:
        self.assertEqual("01:02:03", ts.relogio_por_extenso(3723.9))

    def test_duas_folhas_estimam_o_conjunto(self) -> None:
        um = ts.custo([_registro(segundos=1200.0)], folhas=30, duplas=6)
        self.assertIsNone(um.media_em_segundos)
        self.assertIn("são precisas 2", ts.custo_por_extenso(um))
        dois = ts.custo([_registro(segundos=1200.0), _registro(folha=2, segundos=1800.0)], folhas=30, duplas=6)
        self.assertEqual(1500.0, dois.media_em_segundos)
        self.assertEqual(34, dois.faltam)
        self.assertAlmostEqual(15.0, dois.horas_do_conjunto)

    def test_rascunho_nao_estima(self) -> None:
        self.assertEqual(0, ts.custo([_registro(completa=False), _registro(folha=2, completa=False)], folhas=30, duplas=6).folhas_medidas)


class AcordoTests(unittest.TestCase):
    def test_o_acordo_e_de_caractere(self) -> None:
        self.assertEqual(1.0, ts.acordo_de_caractere("a  b\n", "a b"))
        self.assertAlmostEqual(0.9, ts.acordo_de_caractere("abcdefghij", "abcdefghiX"))
        self.assertEqual(1.0, ts.acordo_de_caractere("", ""))

    def test_acento_conta(self) -> None:
        self.assertLess(ts.acordo_de_caractere("é", "e"), 1.0)

    def test_uma_letra_em_mil_passa_e_duas_voltam(self) -> None:
        base = "a" * 1000
        self.assertTrue(ts.AcordoDaFolha("x", 1, "p", ts.acordo_de_caractere(base, base[:-1] + "b")).aprovada)
        self.assertFalse(ts.AcordoDaFolha("x", 1, "p", ts.acordo_de_caractere(base, base[:-2] + "bb")).aprovada)

    def test_estado_conta_so_a_concluida_do_manifesto(self) -> None:
        m = _manifesto(_folha(), _folha(folha=2, dupla=True))
        pastas = {
            1: {("aaaa", 1): _registro(), ("aaaa", 2): _registro(folha=2, linhas=("igual",)), ("zzzz", 9): _registro("zzzz", 9)},
            2: {("aaaa", 2): _registro(folha=2, passada=2, linhas=("igual",))},
        }
        e = ts.estado_da_verdade(m, pastas)
        self.assertEqual({1: 2, 2: 1}, e.concluidas)
        self.assertEqual({("aaaa", 1), ("aaaa", 2)}, e.prontas)
        self.assertTrue(e.tem_numero)

    def test_rascunho_nao_e_verdade(self) -> None:
        e = ts.estado_da_verdade(_manifesto(_folha()), {1: {("aaaa", 1): _registro(completa=False)}, 2: {}})
        self.assertTrue(e.sem_dados)
        self.assertFalse(e.tem_numero)

    def test_outra_copia_do_livro_nao_conta(self) -> None:
        e = ts.estado_da_verdade(_manifesto(_folha()), {1: {("aaaa", 1): _registro(sha_folha=_SHA_A)}, 2: {}})
        self.assertTrue(e.sem_dados)

    def test_folha_com_acordo_baixo_nao_fica_pronta(self) -> None:
        m = _manifesto(_folha(dupla=True))
        pastas = {1: {("aaaa", 1): _registro(linhas=("certa",))}, 2: {("aaaa", 1): _registro(passada=2, linhas=("outra",))}}
        e = ts.estado_da_verdade(m, pastas)
        self.assertEqual(set(), e.prontas)
        self.assertFalse(e.acordos[0].aprovada)

    def test_imagens_diferentes_nao_se_comparam(self) -> None:
        m = _manifesto(_folha(dupla=True))
        pastas = {1: {("aaaa", 1): _registro()}, 2: {("aaaa", 1): _registro(passada=2, sha_imagem=_SHA_B)}}
        a = ts.estado_da_verdade(m, pastas).acordos[0]
        self.assertIsNone(a.acordo)
        self.assertFalse(a.aprovada)


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)
        self.backup = pasta_temporaria(self)
        ts.declarar_backup(self.pasta, self.backup)

    def _roda(self, *argv: str) -> tuple[int, str]:
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            codigo = texto_prosa.main(list(argv))
        return codigo, saida.getvalue()

    def test_sem_dados_diz_e_nao_zera(self) -> None:
        for argv in (("--conjunto", "scan-ouro", "--acordo"), ("--conjunto", "scan-ouro", "--acordo", "--transcricao", str(pasta_temporaria(self)))):
            with self.subTest(argv=argv):
                codigo, texto = self._roda(*argv)
                self.assertEqual(texto_prosa.SEM_DADOS, codigo)
                self.assertIn("M3 e M4 sem número", texto)
                self.assertIn("não é zero", texto)
                self.assertNotIn("0.00", texto)

    def test_medir_sem_verdade_diz_e_nao_zera(self) -> None:
        codigo, texto = self._roda("--conjunto", "scan-ouro")
        self.assertEqual(texto_prosa.SEM_DADOS, codigo)
        self.assertIn("M3 e M4 sem número", texto)
        codigo, texto = self._roda("--conjunto", "scan-ouro", "--split", "dev", "--transcricao", str(self.pasta), "--dados", str(pasta_temporaria(self) / "d.jsonl"))
        self.assertEqual(texto_prosa.SEM_DADOS, codigo)
        self.assertIn("0 de", texto)

    def test_o_acordo_e_impresso(self) -> None:
        m = scan_ouro.carregar(RAIZ / scan_ouro.CAMINHO)
        duplas = [f for f in m.folhas if f.dupla][:2]
        primeira, segunda = ts.CadernoDaPassada(self.pasta, 1), ts.CadernoDaPassada(self.pasta, 2)
        base = "uma linha digitada com cuidado " * 40
        for k, f in enumerate(duplas):
            comum = {"identidade": f.identidade, "folha": f.folha, "sha_folha": f.sha_folha}
            primeira.gravar(_registro(linhas=(base,), segundos=1200.0, **comum), _doc_cego())
            outra = base if k == 0 else "X" + base[1:-8] + "XXXXXXXX"
            segunda.gravar(_registro(passada=2, linhas=(outra,), segundos=1200.0, **comum), _doc_cego())
        codigo, texto = self._roda("--conjunto", "scan-ouro", "--acordo", "--transcricao", str(self.pasta))
        self.assertEqual(1, codigo, "uma folha abaixo de 99,9% volta")
        self.assertIn("acordo 100.0000% ok", texto)
        self.assertIn("volta para transcrição", texto)
        self.assertIn("M3 e M4 sem número", texto)
        self.assertIn("backup: em_dia", texto)
        self.assertIn("Custo: 00:20:00 por folha", texto)
        self.assertNotIn(base[:20], texto, "texto de livro não sai na tela")

    def test_o_acordo_de_quem_nao_e_scan_ouro_recusa(self) -> None:
        with self.assertRaises(SystemExit):
            self._roda("--conjunto", "ouro", "--acordo")

    def test_o_teste_nao_abre_sem_querer(self) -> None:
        with self.assertRaises(SystemExit):
            self._roda("--conjunto", "scan-ouro", "--split", "teste", "--transcricao", str(self.pasta), "--dados", str(pasta_temporaria(self) / "d.jsonl"))

    def test_a_referencia_e_a_verdade_quando_ha_verdade(self) -> None:
        """Com o split inteiro pronto, a régua mede contra o que foi digitado, e não contra a camada."""
        copia = pasta_temporaria(self) / "scan_ouro.json"
        m = scan_ouro.carregar(RAIZ / scan_ouro.CAMINHO)
        folha = next(f for f in m.do_split(scan_ouro.DEV) if not f.dupla)
        scan_ouro.gravar(replace(m, folhas=(folha,)), copia)
        ts.CadernoDaPassada(self.pasta, 1).gravar(
            _registro(folha.identidade, folha.folha, linhas=("a verdade digitada",), sha_folha=folha.sha_folha), _doc_cego(),
        )
        linha_da_camada = mock.Mock(texto="o ocr de terceiro", bbox=(0.0, 0.0, 9.0, 9.0))
        with (
            mock.patch("chess_diagram_ocr.text.scan_ouro.problemas", return_value=[]),
            mock.patch.object(texto_prosa, "_achar_livros", return_value={folha.identidade: Path("x.pdf")}),
            mock.patch("chess_diagram_ocr.text.leitor.ler_pagina") as ler,
            mock.patch("chess_diagram_ocr.pdf_io.render_pdf_page", return_value=np.zeros((20, 20, 3), np.uint8)),
            mock.patch("chess_diagram_ocr.text.recognizer.build_glyph_recognizer", return_value=object()),
            mock.patch.object(regua_prosa, "linhas_da_pagina", return_value=[linha_da_camada]),
            mock.patch.object(texto_prosa, "_procedencia_dos_motores", return_value={}),
        ):
            ler.return_value = mock.Mock(diagramas=(), avisos=())
            dados = pasta_temporaria(self) / "d.jsonl"
            codigo, _texto = self._roda(
                "--conjunto", "scan-ouro", "--split", "dev", "--motor", "glifo", "--manifesto", str(copia),
                "--transcricao", str(self.pasta), "--dados", str(dados),
            )
        self.assertEqual(0, codigo)
        registro = json.loads(dados.read_text(encoding="utf-8"))
        self.assertEqual("a verdade digitada", registro["ref"])
        self.assertEqual("scan-ouro", registro["conjunto"])
        self.assertEqual(folha.producao, registro["estrato"])


class EscadaPublicadaTests(unittest.TestCase):
    """A tabela da S-745: é contra o melhor degrau que a S-755 compara, e o que não foi medido diz isso por extenso."""

    def setUp(self) -> None:
        self.cru = (RAIZ / "docs/metrics/texto_escada_2026-11-06.json").read_text(encoding="utf-8")
        self.r = json.loads(self.cru)

    def test_o_melhor_degrau_tem_nome_e_numero(self) -> None:
        melhor = self.r["melhor_degrau"]
        self.assertIn("fusao", melhor["nome"])
        self.assertGreater(melhor["ouro_dev_cer_prosa_pct"], 0)
        self.assertIn("sem número", melhor["scan_ouro_dev"])

    def test_os_degraus_que_dependem_de_download_dizem_que_foram_pulados(self) -> None:
        por_degrau = {d["degrau"]: d for d in self.r["escada"]}
        for degrau in ("1", "2", "3"):
            self.assertEqual("pulado por recuo", por_degrau[degrau]["estado"], degrau)
            self.assertNotIn("ouro_dev", por_degrau[degrau], "degrau pulado não tem número")
        for degrau in ("0a", "0b", "0c", "0d"):
            self.assertEqual("sem número", por_degrau[degrau]["scan_ouro_dev"], degrau)

    def test_o_teto_e_o_que_os_ngramas_nao_passam(self) -> None:
        pares = self.r["ngramas"]["ouro_dev"]["pares"]
        self.assertLessEqual(pares["teto - tess_hocr"]["delta_prosa_pp"], pares["ng_10 - tess_hocr"]["delta_prosa_pp"])

    def test_sem_caminho_absoluto_nem_texto_de_livro(self) -> None:
        self.assertNotIn("C:\\\\", self.cru)
        self.assertNotIn('"hip"', self.cru)
        self.assertNotIn('"ref"', self.cru)

    def test_a_chave_de_uso_da_prata_esta_escrita(self) -> None:
        self.assertEqual(prata.USO, self.r["ngramas"]["prata"]["uso"])


if __name__ == "__main__":
    unittest.main()
