"""O `cvoff-texto-prosa` (S-706, S-705, S-713): o teste só abre gravando, o relatório sai sem texto de livro, e duas
corridas dão o mesmo. O leitor é falso: o que se testa aqui é a bancada e o relatório, e não o OCR."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
from ambiente_de_teste import pasta_temporaria

from chess_diagram_ocr.cli import texto_prosa
from chess_diagram_ocr.text import bancada_prosa, ouro, prata, regua_prosa, relatorio_prosa

RAIZ = Path(__file__).resolve().parents[1]
FRASE = "xilofone quimera zabumba"
"""A referência falsa. Se alguma destas palavras chegar ao relatório, é texto de livro no repositório público."""


def _linha(texto: str, y: float = 100.0) -> SimpleNamespace:
    return SimpleNamespace(texto=texto, bbox=(50.0, y, 300.0, y + 12.0))


def _pagina(*textos: str, avisos: tuple = ()) -> SimpleNamespace:
    linhas = [_linha(t, 100.0 + 20 * i) for i, t in enumerate(textos)]
    return SimpleNamespace(
        colunas=[SimpleNamespace(blocos=[SimpleNamespace(linhas=linhas)])],
        cabecalho=None, rodape=None, diagramas=(), avisos=avisos,
    )


class LeitorFalso:
    """No lugar do `ler_pagina`: a camada é a frase, o glifo erra uma letra, e a primeira leitura sai diferente."""

    def __init__(self, ao_ler=None) -> None:
        self.chamadas: list[tuple[int, str]] = []
        self.ao_ler = ao_ler

    def __call__(self, _pdf, indice, *, motor, **_kw):
        if self.ao_ler is not None:
            self.ao_ler()
        self.chamadas.append((indice, motor))
        if motor == "camada":
            return _pagina(FRASE)
        if motor == "camada_prosa":
            return _pagina(FRASE)
        return _pagina("xilofone quimera zabumbo")


class LeitorDeLinhaFalso:
    def ler_linhas(self, recortes, *, lingua, dpi):
        del lingua, dpi
        return SimpleNamespace(linhas=[SimpleNamespace(texto=FRASE) for _ in recortes], falha="")

    def ler_folha(self, cinza, *, lingua, dpi):
        del cinza, lingua, dpi
        return ([SimpleNamespace(texto=FRASE, bloco=1, paragrafo=1, linha=1)], "")


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = pasta_temporaria(self)
        self.manifesto = self.pasta / "ouro.json"
        shutil.copyfile(RAIZ / "assets/texto_prosa/ouro.json", self.manifesto)
        m = ouro.carregar(self.manifesto)
        if m.primeira_leitura_do_teste is not None:  # o versionado já foi aberto pelo G100; aqui ele começa fechado
            from dataclasses import replace

            ouro.gravar(replace(m, primeira_leitura_do_teste=None), self.manifesto)
        self.dados = self.pasta / "d.jsonl"

    def _rodar(self, *argumentos: str, leitor=None) -> tuple[int, str]:
        leitor = leitor or LeitorFalso()
        saida = io.StringIO()
        m = ouro.carregar(self.manifesto)
        p = prata.carregar()
        todos = {f.identidade: Path("livro.pdf") for f in (*m.folhas, *p.folhas)}
        with (
            mock.patch("chess_diagram_ocr.text.leitor.ler_pagina", leitor),
            mock.patch("chess_diagram_ocr.pdf_io.render_pdf_page", lambda *_a, **_k: np.full((50, 50, 3), 255, np.uint8)),
            mock.patch("chess_diagram_ocr.text.recognizer.build_glyph_recognizer", lambda *_a, **_k: object()),
            mock.patch("chess_diagram_ocr.text.ouro.localizar", lambda *_a, **_k: todos),
            mock.patch("chess_diagram_ocr.text.leitor_de_linha.LeitorTesseract", LeitorDeLinhaFalso),
            mock.patch.object(texto_prosa, "codigo_medido", lambda **_k: {"pacote": "x/src", "commit": "c" * 40, "src_sujo": False}),
            contextlib.redirect_stdout(saida),
        ):
            try:
                codigo = texto_prosa.main([*argumentos, "--manifesto", str(self.manifesto)])
            except SystemExit as exc:
                return (-1, str(exc))
        return (codigo, saida.getvalue())

    def _medir_dev(self, *extra: str, dados: Path | None = None) -> tuple[int, str]:
        return self._rodar("--conjunto", "ouro", "--split", "dev", "--motor", "glifo,camada_prosa,tess,tess_oraculo,tess_pagina",
                           "--dados", str(dados or self.dados), *extra)

    def test_o_teste_nao_abre_sem_pedir(self) -> None:
        codigo, texto = self._rodar("--conjunto", "ouro", "--split", "teste", "--motor", "glifo", "--dados", str(self.dados))
        self.assertEqual(-1, codigo)
        self.assertIn("--abrir-teste", texto)
        self.assertFalse(self.dados.exists())
        self.assertIsNone(ouro.carregar(self.manifesto).primeira_leitura_do_teste)

    def test_a_primeira_leitura_e_gravada_antes_de_ler(self) -> None:
        vistas = []
        leitor = LeitorFalso(ao_ler=lambda: vistas.append(ouro.carregar(self.manifesto).primeira_leitura_do_teste))
        codigo, _ = self._rodar("--conjunto", "ouro", "--split", "teste", "--abrir-teste", "--motor", "glifo", "--dados", str(self.dados),
                                "--medido-em", "2026-11-06", "--folhas-maximas", "1", leitor=leitor)
        self.assertEqual(0, codigo)
        self.assertTrue(vistas)
        self.assertEqual({"2026-11-06"}, set(vistas), "uma leitura sem a data gravada abriu o teste em silêncio")

    def test_a_segunda_abertura_nao_muda_a_data(self) -> None:
        for dia in ("2026-11-06", "2026-11-09"):
            self._rodar("--conjunto", "ouro", "--split", "teste", "--abrir-teste", "--motor", "glifo", "--dados", str(self.dados),
                        "--medido-em", dia, "--folhas-maximas", "2")
        self.assertEqual("2026-11-06", ouro.carregar(self.manifesto).primeira_leitura_do_teste)

    def test_o_teste_nao_imprime_numero_por_folha(self) -> None:
        _, texto = self._rodar("--conjunto", "ouro", "--split", "teste", "--abrir-teste", "--motor", "glifo", "--dados", str(self.dados),
                               "--medido-em", "2026-11-06", "--folhas-maximas", "2")
        self.assertIn("1/2", texto)
        self.assertNotIn("glifo=", texto)
        _, texto = self._medir_dev("--folhas-maximas", "1", dados=self.pasta / "dev.jsonl")
        self.assertIn("glifo=", texto)

    def test_dados_dentro_do_repositorio_sao_recusados(self) -> None:
        with mock.patch.object(texto_prosa, "_pasta_do_repositorio", lambda: self.pasta):
            (self.pasta / ".git").mkdir()
            with self.assertRaisesRegex(SystemExit, "texto de livro"):
                texto_prosa.recusar_dentro_do_repositorio(self.pasta / "d.jsonl")

    def test_aquecimento_e_descartado_uma_vez_por_processo(self) -> None:
        leitor = LeitorFalso()
        self._rodar("--conjunto", "ouro", "--split", "dev", "--motor", "glifo", "--dados", str(self.dados), "--folhas-maximas", "2", leitor=leitor)
        self.assertEqual(leitor.chamadas[0][1], "glifo")
        registros = [json.loads(x) for x in self.dados.open(encoding="utf-8")]
        self.assertEqual(2, len(registros))
        # aquecimento + (camada, glifo, motor) por folha
        self.assertEqual(1 + 3 * 2, len(leitor.chamadas))

    def test_medir_continua_de_onde_parou(self) -> None:
        self._medir_dev("--folhas-maximas", "3")
        self.assertEqual(3, sum(1 for _ in self.dados.open(encoding="utf-8")))
        _, texto = self._medir_dev("--folhas-maximas", "5")
        self.assertIn("2 a medir", texto)
        chaves = [(r["identidade"], r["folha"]) for r in map(json.loads, self.dados.open(encoding="utf-8"))]
        self.assertEqual(5, len(set(chaves)))

    def test_limite_de_tempo_para_e_avisa(self) -> None:
        codigo, texto = self._medir_dev("--limite-segundos", "0.000001", "--folhas-maximas", "3")
        self.assertEqual(3, codigo)
        self.assertIn("parou pelo limite", texto)

    def test_motor_desconhecido_levanta(self) -> None:
        codigo, texto = self._rodar("--conjunto", "ouro", "--motor", "nenhum", "--dados", str(self.dados))
        self.assertEqual(-1, codigo)
        self.assertIn("motor desconhecido", texto)

    def test_cada_folha_traz_codigo_e_procedencia(self) -> None:
        self._medir_dev("--folhas-maximas", "1")
        r = json.loads(self.dados.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual("x/src", r["codigo"]["pacote"])
        self.assertEqual("c" * 40, r["codigo"]["commit"])
        self.assertIn("modelo_sha256", r["codigo"])

    def test_degradar_usa_a_semente_da_folha(self) -> None:
        dados = self.pasta / "deg.jsonl"
        self._medir_dev("--degradar", "medio", "--folhas-maximas", "1", dados=dados)
        self.assertEqual("medio", json.loads(dados.read_text(encoding="utf-8").splitlines()[0])["perfil"])

    def test_compila_sem_texto_de_livro_e_sem_caminho(self) -> None:
        self._medir_dev()
        saida = self.pasta / "r.json"
        codigo, tela = self._rodar("--compilar", str(saida), "--bloco", f"ouro_dev={self.dados}", "--medido-em", "2026-11-06")
        self.assertEqual(0, codigo)
        cru = saida.read_text(encoding="utf-8")
        for palavra in FRASE.split():
            if len(palavra) > 1:
                self.assertNotIn(palavra, cru)
        self.assertNotIn("zabumbo", cru)
        self.assertNotIn(str(self.pasta).replace("\\", "/"), cru.replace("\\\\", "/"))
        relatorio = json.loads(cru)
        bloco = relatorio["conjuntos"]["ouro_dev"]
        self.assertEqual(27, bloco["folhas"])
        self.assertEqual(5, bloco["livros"])
        self.assertEqual(regua_prosa.VERSAO_CLASSIFICADOR, relatorio["regua"]["classificador"])
        self.assertIn("segundos_por_folha", bloco)
        self.assertIn("CER prosa", tela)
        self.assertEqual({"glifo", "camada_prosa", "tess", "tess_oraculo", "tess_pagina"}, set(bloco["motores"]))
        self.assertEqual({"tip", "cru"}, set(bloco["motores"]["glifo"]))
        self.assertGreater(bloco["motores"]["glifo"]["tip"]["cer_prosa"], 0)
        self.assertEqual(0, bloco["motores"]["camada_prosa"]["tip"]["cer_prosa"])
        self.assertEqual(27, sum(len(g["folhas"]) for g in bloco["codigo_das_folhas"]))
        self.assertIn("letra trocada", bloco["taxonomia"]["glifo"]["familias"])

    def test_duas_corridas_iguais_fora_o_tempo(self) -> None:
        relatorios = []
        for i in (1, 2):
            dados = self.pasta / f"c{i}.jsonl"
            self._medir_dev("--folhas-maximas", "6", dados=dados)
            saida = self.pasta / f"c{i}.json"
            self._rodar("--compilar", str(saida), "--bloco", f"ouro_dev={dados}", "--medido-em", "2026-11-06")
            relatorios.append(saida)
        codigo, texto = self._rodar("--comparar", str(relatorios[0]), str(relatorios[1]))
        self.assertEqual(0, codigo, texto)
        self.assertIn("0 diferenças", texto)

    def test_comparar_acusa_diferenca_fora_o_tempo(self) -> None:
        a, b = self.pasta / "a.json", self.pasta / "b.json"
        a.write_text(json.dumps({"x": 1, "segundos_por_folha": {"g": 1.0}}), encoding="utf-8")
        b.write_text(json.dumps({"x": 2, "segundos_por_folha": {"g": 9.0}}), encoding="utf-8")
        codigo, texto = self._rodar("--comparar", str(a), str(b))
        self.assertEqual(1, codigo)
        self.assertIn("1 diferenças", texto)
        b.write_text(json.dumps({"x": 1, "segundos_por_folha": {"g": 9.0}}), encoding="utf-8")
        self.assertEqual(0, self._rodar("--comparar", str(a), str(b))[0])

    def test_filtro_vai_escrito_no_relatorio(self) -> None:
        self._medir_dev()
        saida = self.pasta / "r.json"
        self._rodar("--compilar", str(saida), "--bloco", f"x={self.dados}?oraculo_max=0.10&estrato=prosa")
        bloco = json.loads(saida.read_text(encoding="utf-8"))["conjuntos"]["x"]
        self.assertEqual({"oraculo_max": 0.1, "estrato": "prosa"}, bloco["filtro"])
        self.assertLess(bloco["folhas"], 27)

    def test_importar_acrescenta_motor_com_a_mesma_referencia(self) -> None:
        self._medir_dev("--folhas-maximas", "2")
        registros = [json.loads(x) for x in self.dados.open(encoding="utf-8")]
        externas = self.pasta / "suite.jsonl"
        externas.write_text("\n".join(json.dumps({"identidade": r["identidade"], "folha": r["folha"], "texto": FRASE}) for r in registros), encoding="utf-8")
        saida = self.pasta / "com_suite.jsonl"
        codigo, _ = self._rodar("--importar", f"suite={externas}", "--dados", str(self.dados), "--saida", str(saida))
        self.assertEqual(0, codigo)
        novo = json.loads(saida.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(0, novo["placar"]["suite|tip"]["erros"]["prosa"])
        self.assertIn("glifo|tip", novo["placar"])

    def test_importar_recusa_motor_que_nao_leu_tudo(self) -> None:
        self._medir_dev("--folhas-maximas", "2")
        externas = self.pasta / "suite.jsonl"
        externas.write_text("", encoding="utf-8")
        codigo, texto = self._rodar("--importar", f"suite={externas}", "--dados", str(self.dados), "--saida", str(self.pasta / "s.jsonl"))
        self.assertEqual(-1, codigo)
        self.assertIn("não leu", texto)

    def test_repontuar_refaz_pelo_texto(self) -> None:
        self._medir_dev("--folhas-maximas", "1")
        saida = self.pasta / "rep.jsonl"
        self.assertEqual(0, self._rodar("--repontuar", str(self.dados), "--saida", str(saida))[0])
        a = json.loads(self.dados.read_text(encoding="utf-8").splitlines()[0])
        b = json.loads(saida.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(a["placar"], b["placar"])

    def test_motor_registrado_entra_na_bancada(self) -> None:
        """A porta da S-721: uma função sobre a folha vira `--motor nome`, com a mesma referência e o mesmo placar."""
        bancada_prosa.registrar_motor("meu", lambda folha: FRASE)
        self.addCleanup(bancada_prosa.MOTORES_DE_BANCADA.pop, "meu", None)
        codigo, _ = self._rodar("--conjunto", "ouro", "--split", "dev", "--motor", "meu", "--dados", str(self.dados), "--folhas-maximas", "1")
        self.assertEqual(0, codigo)
        r = json.loads(self.dados.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(0, r["placar"]["meu|tip"]["erros"]["prosa"])

    def test_motor_de_linha_le_as_caixas_do_glifo(self) -> None:
        folha = bancada_prosa.FolhaEmMedida(
            pdf="x", indice=0, lingua="eng", dpi=220, imagem=np.full((3000, 3000, 3), 255, np.uint8), reconhecedor=None,
            referencia=_pagina(FRASE), glifo=_pagina("um", "dois"), linhas_da_referencia=[], diagramas=[],
        )
        self.assertEqual(f"{FRASE}\n{FRASE}", bancada_prosa.motor_de_linha(LeitorDeLinhaFalso())(folha))


def _registro(identidade: str, folha: int, *, conjunto: str = "ouro", split: str = "dev", perfil: str = "", estrato: str = "prosa",
              motores: dict[str, str] | None = None) -> dict:
    hip = motores or {"glifo": "a casa"}
    ref = "a casa"
    return {
        "conjunto": conjunto, "split": split, "perfil": perfil, "identidade": identidade, "folha": folha, "lingua": "por", "estrato": estrato,
        "ref": ref, "hip": hip, "placar": bancada_prosa.pontuar_hipoteses(ref, hip, "por"), "tempo": dict.fromkeys(hip, 1.0), "avisos": {},
        "preservacao": {}, "n_linhas": {"ref": 1, "ref_no_diagrama": 0, "glifo": 1},
        "codigo": {"pacote": "x/src", "commit": "c", "src_sujo": False},
    }


class BlocoTests(unittest.TestCase):
    def _folhas(self, **kw) -> list[dict]:
        return [_registro(livro, f, **kw) for livro in ("a", "b") for f in (1, 2)]

    def test_a_prata_nunca_se_soma_ao_ouro(self) -> None:
        with self.assertRaisesRegex(ValueError, "nunca se soma"):
            relatorio_prosa.compilar_bloco([_registro("a", 1), _registro("b", 1, conjunto="prata", split="", estrato="clearscan")])

    def test_degradado_nao_se_soma_ao_limpo(self) -> None:
        with self.assertRaisesRegex(ValueError, "nunca se soma"):
            relatorio_prosa.compilar_bloco([_registro("a", 1), _registro("a", 2, perfil="medio")])

    def test_dev_nao_se_soma_ao_teste(self) -> None:
        with self.assertRaisesRegex(ValueError, "nunca se soma"):
            relatorio_prosa.compilar_bloco([_registro("a", 1), _registro("b", 1, split="teste")])

    def test_todo_numero_prata_leva_a_palavra(self) -> None:
        bloco = relatorio_prosa.compilar_bloco(self._folhas(conjunto="prata", split="", estrato="clearscan", motores={"glifo": "a cosa", "tess": "a casa", "tess_oraculo": "a casa", "tess_pagina": "a casa"}))
        self.assertEqual(prata.USO, bloco["uso"])
        pendentes = []

        def varrer(no, caminho=""):
            if isinstance(no, dict):
                if any(str(k).startswith(("cer_", "wer_", "delta_pp", "figurina_")) for k in no) and no.get("uso") != prata.USO:
                    pendentes.append(caminho)
                for k, v in no.items():
                    varrer(v, f"{caminho}.{k}")

        varrer(bloco)
        self.assertEqual([], pendentes)
        self.assertIn(prata.USO, bloco["motores"]["glifo"]["tip"]["uso"])
        self.assertIn(prata.USO, bloco["por_livro"]["a"]["motores"]["glifo"]["uso"])
        self.assertIn(prata.USO, bloco["por_estrato"]["clearscan"]["motores"]["glifo"]["uso"])

    def test_a_tela_da_prata_diz_ordenacao_em_cada_numero(self) -> None:
        bloco = relatorio_prosa.compilar_bloco(self._folhas(conjunto="prata", split="", estrato="de_300"))
        linhas = relatorio_prosa.linhas_na_tela("prata", bloco)
        self.assertGreaterEqual(linhas[1].count(prata.USO), 3)

    def test_o_ouro_nao_diz_ordenacao(self) -> None:
        bloco = relatorio_prosa.compilar_bloco(self._folhas())
        self.assertNotIn(prata.USO, json.dumps(bloco, ensure_ascii=False))

    def test_a_prata_sai_pelos_tres_estratos(self) -> None:
        folhas = [_registro(f"l{e}", 1, conjunto="prata", split="", estrato=e) for e in prata.ESTRATOS]
        self.assertEqual(set(prata.ESTRATOS), set(relatorio_prosa.compilar_bloco(folhas)["por_estrato"]))

    def test_o_teste_nao_publica_livro_nem_palavra(self) -> None:
        bloco = relatorio_prosa.compilar_bloco(self._folhas(split="teste", motores={"glifo": "a cosa"}))
        self.assertNotIn("por_livro", bloco)
        self.assertNotIn("livros", bloco["taxonomia"]["glifo"]["familias"]["letra trocada"])
        self.assertIn("pior_livro_sem_nome", bloco)
        self.assertNotIn("cosa", json.dumps(bloco, ensure_ascii=False))

    def test_perda_de_leiaute_por_livro_com_ic_e_tess_pagina(self) -> None:
        motores = {"tess": "a cosa", "tess_oraculo": "a casa", "tess_pagina": "a coso"}
        bloco = relatorio_prosa.compilar_bloco(self._folhas(motores=motores))
        perda = bloco["perda_de_leiaute"]
        self.assertGreater(perda["delta_pp"], 0)
        self.assertEqual(2, len(perda["ic95_pp"]))
        self.assertIn("cer_tess_pagina", perda)
        self.assertEqual({"a", "b"}, set(perda["por_livro"]))
        for item in perda["por_livro"].values():
            self.assertIn("ic95_pp", item)
            self.assertIn("cer_tess_pagina", item)

    def test_sem_os_dois_leitores_nao_ha_perda(self) -> None:
        self.assertNotIn("perda_de_leiaute", relatorio_prosa.compilar_bloco(self._folhas()))

    def test_par_pedido_entra(self) -> None:
        bloco = relatorio_prosa.compilar_bloco(self._folhas(motores={"x": "a casa", "y": "a cosa"}), pares=[("x", "y")])
        self.assertLess(bloco["pares"]["x - y (prosa)"]["delta_pp"], 0)

    def test_filtro_desconhecido_levanta(self) -> None:
        with self.assertRaises(ValueError):
            relatorio_prosa.filtrar(self._folhas(), {"nada": 1})

    def test_filtro_que_nao_deixa_folha_levanta(self) -> None:
        with self.assertRaises(ValueError):
            relatorio_prosa.compilar_bloco(self._folhas(), filtro={"so_livro": ["z"]})

    def test_folha_perdida_sai_pelo_filtro_e_o_motivo_fica(self) -> None:
        folhas = self._folhas()
        folhas[0]["n_linhas"] = {"ref": 30, "ref_no_diagrama": 0, "glifo": 1}
        ficam, fora = relatorio_prosa.filtrar(folhas, {"sem_folha_perdida": True})
        self.assertEqual(3, len(ficam))
        self.assertEqual("folha perdida pelo leiaute", fora[0]["motivo"])

    def test_achatar_tira_so_as_chaves_de_tempo(self) -> None:
        self.assertEqual({"a.b": 1, "c.0.d": 2}, relatorio_prosa.achatar({"a": {"b": 1, "segundos_x": 3}, "c": [{"d": 2}], "segundos_por_folha": {"e": 1}}))


class EntradaTests(unittest.TestCase):
    def test_o_comando_esta_no_pyproject(self) -> None:
        self.assertIn('cvoff-texto-prosa = "chess_diagram_ocr.cli.texto_prosa:main"', (RAIZ / "pyproject.toml").read_text(encoding="utf-8"))

    def test_o_comando_responde_ajuda(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as saida, self.assertRaises(SystemExit):
            texto_prosa.main(["--help"])
        self.assertIn("--abrir-teste", saida.getvalue())

    def test_jsonl_de_medicao_nao_mora_em_docs(self) -> None:
        self.assertEqual([], [str(c) for c in (RAIZ / "docs/metrics").glob("texto_prosa*/**/*.jsonl")])


if __name__ == "__main__":
    unittest.main()
