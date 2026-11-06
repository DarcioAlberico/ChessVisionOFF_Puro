"""A confiança calibrada por palavra e a marca por corte (S-760, S-761): decisão com tokens sintéticos, fiação com leitor falso."""

from __future__ import annotations

import ast
import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from chess_diagram_ocr.text import confianca_palavra as cp
from chess_diagram_ocr.text import fila, fusao, leitor, ouro
from chess_diagram_ocr.text.boxes import Caixa
from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida

RAIZ = Path(__file__).resolve().parents[1]
FONTE = RAIZ / "src" / "chess_diagram_ocr" / "text"


def existe(token: str) -> bool:
    return token.strip(".,;:") in {"the", "white", "king", "moves"}


def token(texto: str, origem: str = "outro", do_glifo: str | None = None, conf: float | None = 0.96, do_leitor: str | None = None) -> fusao.Token:
    return fusao.Token(texto, origem, texto if do_glifo is None else do_glifo, conf, texto if do_leitor is None else do_leitor)


class AtributosTests(unittest.TestCase):
    def test_um_valor_por_nome_e_um_peso_por_nome(self) -> None:
        self.assertEqual(len(cp.atributos(token("the"), existe=existe)), len(cp.NOMES))
        for dominio in cp.DOMINIOS:
            self.assertEqual(len(cp.COEFICIENTES[dominio]), len(cp.NOMES))

    def test_o_dominio_e_o_estrato_da_fusao(self) -> None:
        self.assertEqual(cp.dominio_da_regra(fusao.V3), cp.SCAN)
        self.assertEqual(cp.dominio_da_regra(fusao.V5), cp.DIGITAL)

    def test_a_palavra_em_que_os_dois_concordam_vale_mais_que_a_discordada(self) -> None:
        for dominio in cp.DOMINIOS:
            certa = cp.erro_de(cp.atributos(token("the"), existe=existe), dominio)
            duvidosa = cp.erro_de(cp.atributos(token("wbite", do_glifo="while", conf=0.5), existe=existe), dominio)
            self.assertLess(certa, duvidosa, dominio)

    def test_fora_do_lexico_pesa(self) -> None:
        for dominio in cp.DOMINIOS:
            dentro = cp.erro_de(cp.atributos(token("king"), existe=existe), dominio)
            fora = cp.erro_de(cp.atributos(token("kirg"), existe=existe), dominio)
            self.assertLess(dentro, fora, dominio)

    def test_a_notacao_vale_menos_erro_que_a_prosa_igual_de_duvidosa(self) -> None:
        """A referência da notação é a camada: o calibrador não pode pintá-la de suspeita por escrever `Nf3`."""
        for dominio in cp.DOMINIOS:
            lance = cp.erro_de(cp.atributos(token("Nf3", conf=0.5), existe=existe), dominio)
            palavra = cp.erro_de(cp.atributos(token("kirg", conf=0.5), existe=existe), dominio)
            self.assertLess(lance, palavra, dominio)


class CalibrarFolhaTests(unittest.TestCase):
    def test_nenhum_texto_muda(self) -> None:
        linhas = [[token("the"), token("wbite", do_glifo="white", conf=0.3)], [token("Nf3", "glifo", conf=0.9)]]
        saida, erros = cp.calibrar_folha(linhas, existe=existe, dominio=cp.DIGITAL)
        self.assertEqual([[t.texto for t in ln] for ln in saida], [[t.texto for t in ln] for ln in linhas])
        self.assertEqual([len(e) for e in erros], [2, 1])

    def test_a_prosa_recebe_a_confianca_calibrada_e_o_lance_fica_com_a_de_quem_escreveu(self) -> None:
        saida, erros = cp.calibrar_folha([[token("wbite", do_glifo="white", conf=0.96), token("Nf3", "glifo", conf=0.42)]], existe=existe, dominio=cp.DIGITAL)
        self.assertAlmostEqual(saida[0][0].confianca, 1.0 - erros[0][0])
        self.assertEqual(saida[0][1].confianca, 0.42)

    def test_a_linha_vale_a_palavra_mais_fraca_e_sem_prosa_a_de_antes(self) -> None:
        self.assertEqual(cp.confianca_da_linha([token("the", conf=0.9), token("king", conf=0.4), token("Nf3", "glifo", conf=0.1)], 0.7), 0.4)
        self.assertEqual(cp.confianca_da_linha([token("Nf3", "glifo", conf=0.1)], 0.7), 0.7)


class PublicadoTests(unittest.TestCase):
    """**Número que ninguém mediu não entra pela constante.** Mudar o V3 para 0,3 passava em 397 testes: as duas tabelas têm de bater com o relatório, como `ALARMES` na S-763."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.relatorio = json.loads((RAIZ / "docs" / "metrics" / "texto_confianca_2026-11-06.json").read_text(encoding="utf-8"))
        cls.blocos = cls.relatorio["s760_s761_calibrador_e_marca"]

    def test_os_coeficientes_sao_os_publicados(self) -> None:
        for dominio in cp.DOMINIOS:
            self.assertEqual(dict(zip(cp.NOMES, cp.COEFICIENTES[dominio], strict=True)), self.blocos[dominio]["pesos"], dominio)

    def test_o_corte_e_o_publicado(self) -> None:
        self.assertEqual(fusao.CORTE_DE_REVISAR[fusao.V5], self.blocos[cp.DIGITAL]["corte_de_revisar"])
        self.assertEqual(fusao.CORTE_DE_REVISAR[fusao.V3], self.blocos[cp.SCAN]["corte_de_revisar"])

    def test_o_relatorio_diz_com_que_arvore_foi_medido(self) -> None:
        for chave in ("coleta_que_ajustou", "marca_no_produto"):
            codigo = self.relatorio["codigo"][chave]
            self.assertEqual(len(codigo["commit"]), 1, chave)
            self.assertFalse(codigo["src_sujo"], chave)
            self.assertEqual(len(codigo["modelo_sha256"]), 1, chave)
            self.assertTrue(all(codigo["modelo_sha256"]), chave)
        linguas = set(self.relatorio["codigo"]["coleta_que_ajustou"]["tessdata_sha256"])
        self.assertLessEqual({"eng", "por", "deu", "fra", "spa", "nld"}, linguas, "o scan tem dez livros: as línguas de todos")

    def test_o_commit_contem_o_calibrador(self) -> None:
        for chave in ("coleta_que_ajustou", "marca_no_produto"):
            commit = self.relatorio["codigo"][chave]["commit"][0]
            achado = subprocess.run(["git", "-C", str(RAIZ), "cat-file", "-e", f"{commit}:src/chess_diagram_ocr/text/confianca_palavra.py"], capture_output=True, check=False)
            if achado.returncode == 128 and b"not a git repository" in achado.stderr:
                self.skipTest("sem git nesta árvore")
            self.assertEqual(achado.returncode, 0, f"{chave}: {commit} não tem o calibrador")

    def test_o_ajuste_nao_tocou_em_livro_do_teste_nem_da_serie_dele(self) -> None:
        exclusao = ouro.carregar_exclusao().identidades
        do_teste = {livro.identidade for livro in ouro.carregar().livros if livro.split == ouro.TESTE}
        for dominio in cp.DOMINIOS:
            ajuste = set(self.blocos[dominio]["ajuste"]["identidades"])
            self.assertTrue(ajuste)
            self.assertFalse(ajuste & exclusao, dominio)
            self.assertFalse(ajuste & do_teste, dominio)


class MarcaPorCorteTests(unittest.TestCase):
    def test_o_corte_e_da_fusao_e_nao_do_ocr(self) -> None:
        """A S-761 é explícita: o `ocr.MIN_CONFIDENCE` está no digest da S-218, e o `pdf_pesquisavel` e a `coleta` o usam."""
        arvore = ast.parse((FONTE / "fusao.py").read_text(encoding="utf-8"))
        importados = [n.module or "" for n in ast.walk(arvore) if isinstance(n, ast.ImportFrom)] + [
            a.name for n in ast.walk(arvore) if isinstance(n, ast.Import) for a in n.names
        ]
        self.assertFalse([m for m in importados if "ocr" in m])
        self.assertEqual(set(fusao.CORTE_DE_REVISAR), set(fusao.REGRAS))
        for valor in fusao.CORTE_DE_REVISAR.values():
            self.assertTrue(0.0 < valor < 1.0)

    def test_marca_o_que_passa_do_corte_e_folha_limpa_nao_marca_nada(self) -> None:
        self.assertEqual(fusao.marcar_por_erro([[0.5, 0.01], [0.2]], 0.1), [frozenset({0}), frozenset({0})])
        self.assertEqual(fusao.marcar_por_erro([[0.001] * 50], 0.1), [frozenset()])

    def test_a_folha_ruim_pode_passar_do_teto_da_folha(self) -> None:
        """O teto por folha deixava marca sobrando na folha limpa e faltando na ruim: 35% contra 56% na prata."""
        self.assertEqual(len(fusao.marcar_por_erro([[0.9] * 40], 0.1)[0]), 40)


def _cru(texto: str, y: int = 10) -> leitor._Cru:  # noqa: SLF001
    return leitor._Cru(texto=texto, caixa=Caixa(0, y, 400, y + 20), confianca=0.77, procedencia="glifo", confiancas=tuple(0.99 for _ in texto.replace(" ", "")))  # noqa: SLF001


class FiacaoTests(unittest.TestCase):
    def _ler(self, *, regra: str = fusao.V5, marca: bool = True) -> list[leitor._Cru]:  # noqa: SLF001
        return leitor._com_prosa_de_outro_leitor(  # noqa: SLF001
            [_cru("the wbite king moves", 10), _cru("the king", 40)],
            [("the wlnte king moves", (0.96, 0.4, 0.96, 0.96), ()), ("the king", (0.96, 0.96), ())],
            existe=existe,
            e_da_camada=False,
            marca_por_palavra=marca,
            regra=regra,
        )

    def test_a_palavra_duvidosa_e_a_marcada_e_a_certa_nao(self) -> None:
        primeira, segunda = self._ler()
        self.assertEqual(primeira.texto, "the wlnte king moves")
        marcadas = [primeira.texto[a:b] for a, b in primeira.revisar_em]
        self.assertEqual(marcadas, ["wlnte"])
        self.assertEqual(segunda.revisar_em, ())

    def test_a_linha_fundida_nao_carrega_mais_a_confianca_do_glifo(self) -> None:
        primeira, _ = self._ler()
        self.assertNotEqual(primeira.confianca, 0.77)
        valores = [v for _, _, v in primeira.confianca_em]
        self.assertEqual(primeira.confianca, min(valores))

    def test_a_marca_desligada_nao_marca_e_a_calibracao_fica(self) -> None:
        primeira, _ = self._ler(marca=False)
        self.assertEqual(primeira.revisar_em, ())
        self.assertLess(primeira.confianca, 0.77)

    def test_o_interruptor_desligado_volta_a_de_antes(self) -> None:
        with mock.patch.object(cp, "LIGADO", False):
            primeira, _ = self._ler()
        self.assertEqual(primeira.confianca, 0.77)
        self.assertIn(0.4, [v for _, _, v in primeira.confianca_em])

    def test_o_interruptor_nao_muda_texto(self) -> None:
        ligado = [c.texto for c in self._ler()]
        with mock.patch.object(cp, "LIGADO", False):
            desligado = [c.texto for c in self._ler()]
        self.assertEqual(ligado, desligado)

    def test_prosa_da_camada_nao_passa_pelo_calibrador(self) -> None:
        saida = leitor._com_prosa_de_outro_leitor(  # noqa: SLF001
            [_cru("the wbite king")], [("the white king", (), ())], existe=fusao.existe_na_camada(existe), e_da_camada=True, marca_por_palavra=True,
        )
        self.assertEqual(saida[0].confianca, 1.0)
        self.assertEqual(saida[0].revisar_em, ())
        self.assertEqual(saida[0].confianca_em, ())


class ConsumidoresTests(unittest.TestCase):
    def _pagina(self, linha: LinhaLida) -> PaginaLida:
        return PaginaLida(documento="x.pdf", pagina=3, largura=100.0, altura=100.0, unidade="pt", colunas=(Coluna(indice=0, blocos=(BlocoDeTexto(linhas=(linha,)),)),))

    def test_a_fila_traz_a_palavra_e_nao_a_linha_quando_a_linha_sabe_dizer(self) -> None:
        linha = LinhaLida("the wlnte king", (0.0, 0.0, 10.0, 10.0), confianca=0.2, procedencia="tesseract", confianca_em=((0, 3, 0.99), (4, 9, 0.2), (10, 14, 0.98)))
        itens = fila.de_pagina(self._pagina(linha))
        self.assertEqual([i.texto for i in itens], ["wlnte"])
        self.assertEqual(itens[0].confianca, 0.2)
        self.assertEqual(itens[0].box, 1)

    def test_a_palavra_marcada_entra_mesmo_com_faixa_tranquila_e_fica_atras_da_vermelha(self) -> None:
        linha = LinhaLida(
            "the wlnte king", (0.0, 0.0, 10.0, 10.0), confianca=0.2, procedencia="tesseract",
            confianca_em=((0, 3, 0.99), (4, 9, 0.2), (10, 14, 0.97)), revisar_em=((4, 9), (10, 14)),
        )
        self.assertEqual([i.texto for i in fila.de_pagina(self._pagina(linha))], ["wlnte", "king"])

    def test_a_linha_sem_detalhe_continua_como_era(self) -> None:
        linha = LinhaLida("the wlnte king", (0.0, 0.0, 10.0, 10.0), confianca=0.2, procedencia="glifo")
        itens = fila.de_pagina(self._pagina(linha))
        self.assertEqual([(i.texto, i.box) for i in itens], [("the wlnte king", -1)])

    def test_a_cor_e_a_ordem_seguem_o_mesmo_numero(self) -> None:
        linha = LinhaLida("aa bb", (0.0, 0.0, 10.0, 10.0), confianca=0.1, procedencia="tesseract", confianca_em=((0, 2, 0.5), (3, 5, 0.1)))
        itens = fila.de_pagina(self._pagina(linha))
        self.assertEqual([i.texto for i in itens], ["bb", "aa"])
        self.assertEqual([i.faixa for i in itens], ["revisar", "conferir"])

    def test_o_grafo_nao_alcanca_a_regua(self) -> None:
        arvore = ast.parse((FONTE / "confianca_palavra.py").read_text(encoding="utf-8"))
        nomes = [a.name for n in ast.walk(arvore) if isinstance(n, ast.ImportFrom) for a in n.names] + [n.module or "" for n in ast.walk(arvore) if isinstance(n, ast.ImportFrom)]
        self.assertFalse({"regua_prosa", "relatorio_prosa", "bancada_prosa"} & set(nomes))


if __name__ == "__main__":
    unittest.main()
