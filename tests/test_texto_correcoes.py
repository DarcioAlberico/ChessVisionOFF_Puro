"""A correção humana: o que ela carimba, e o que ela conta (S-239).

`Procedencia` tem `"humano"` desde a S-201 e nada o escrevia. O que este arquivo afirma é a regra
que faz a correção chegar até a fila da S-212: **o que está na tela comparado com o que o motor
leu**, em pares mínimos -- e nunca um rótulo escrito na base sem revisão.
"""

from __future__ import annotations

import ast
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from chess_diagram_ocr.cli import texto_correcoes
from chess_diagram_ocr.text import arquivo, correcao, rico
from chess_diagram_ocr.text.pagina import (
    BlocoDeDiagrama,
    BlocoDeTexto,
    Coluna,
    LinhaLida,
    PaginaLida,
)


def _texto(conteudo: str, procedencia: str = "glifo", confianca: float = 0.9) -> BlocoDeTexto:
    return BlocoDeTexto.de_linhas(
        [LinhaLida(conteudo, (0.0, 0.0, 10.0, 10.0), confianca, procedencia)]  # type: ignore[arg-type]
    )


def _pagina(*blocos: object) -> PaginaLida:
    return PaginaLida(colunas=(Coluna(indice=0, blocos=tuple(blocos)),))  # type: ignore[arg-type]


def _editado(doc: rico.DocumentoRico, bloco: int, novo: str) -> rico.DocumentoRico:
    """O documento com o texto daquele bloco trocado -- o que o widget devolveria depois da edição."""
    corridas = tuple(
        replace(c, texto=novo) if c.bloco == bloco else c for c in doc.corridas
    )
    return rico.DocumentoRico(corridas=corridas, origem=doc.origem)


class CarimboTests(unittest.TestCase):
    def test_a_corrida_editada_vira_humano(self) -> None:
        doc = rico.de_pagina(_pagina(_texto("Black,s move")))
        marcado = correcao.com_procedencia_humana(_editado(doc, 0, "Black's move"))
        self.assertEqual(marcado.corridas[0].procedencia, "humano")

    def test_a_corrida_intocada_mantem_o_motor(self) -> None:
        doc = rico.de_pagina(_pagina(_texto("intacto")))
        self.assertEqual(correcao.com_procedencia_humana(doc).corridas[0].procedencia, "glifo")

    def test_so_o_bloco_editado_e_carimbado(self) -> None:
        doc = rico.de_pagina(_pagina(_texto("um"), _texto("dois")))
        marcado = correcao.com_procedencia_humana(_editado(doc, 1, "DOIS"))
        por_bloco = {c.bloco: c.procedencia for c in marcado.corridas if c.bloco != rico.SEM_BLOCO}
        self.assertEqual(por_bloco, {0: "glifo", 1: "humano"})

    def test_o_texto_escrito_do_zero_e_humano(self) -> None:
        """Sem bloco de origem, ninguém leu aquilo: a mão escreveu."""
        doc = rico.DocumentoRico(corridas=(rico.Corrida(texto="digitado"),))
        self.assertEqual(correcao.com_procedencia_humana(doc).corridas[0].procedencia, "humano")

    def test_o_separador_nao_vira_humano(self) -> None:
        """Ele é estrutura que o leitor produziu, e ninguém o escreveu."""
        doc = rico.de_pagina(_pagina(_texto("um"), _texto("dois")))
        marcado = correcao.com_procedencia_humana(doc)
        separadores = [c for c in marcado.corridas if c.tipo == rico.SEPARADOR]
        self.assertEqual([c.procedencia for c in separadores], [None])

    def test_a_marcacao_e_idempotente(self) -> None:
        """`documento_atual` a aplica a cada gravação; ela não pode acumular efeito."""
        doc = correcao.com_procedencia_humana(
            _editado(rico.de_pagina(_pagina(_texto("antes"))), 0, "depois")
        )
        self.assertEqual(correcao.com_procedencia_humana(doc), doc)

    def test_a_marcacao_nao_toca_no_que_o_motor_leu(self) -> None:
        """É a `PaginaLida` que continua sabendo quem errou -- e é ela a régua da comparação."""
        doc = rico.de_pagina(_pagina(_texto("antes")))
        marcado = correcao.com_procedencia_humana(_editado(doc, 0, "depois"))
        assert marcado.origem is not None
        self.assertEqual(marcado.origem.blocos[0].procedencia, "glifo")
        self.assertEqual(marcado.origem.blocos[0].texto, "antes")


class ParMinimoTests(unittest.TestCase):
    def test_o_par_e_o_trecho_que_mudou_e_nao_o_bloco(self) -> None:
        """A S-213 quer saber quantas vezes a vírgula virou apóstrofo, não quantos parágrafos."""
        doc = rico.de_pagina(_pagina(_texto("In Black,s position the rook is lost")))
        achadas = correcao.correcoes(_editado(doc, 0, "In Black's position the rook is lost"))
        self.assertEqual([(c.antes, c.depois) for c in achadas], [(",", "'")])

    def test_duas_trocas_no_mesmo_bloco_dao_dois_pares(self) -> None:
        doc = rico.de_pagina(_pagina(_texto("a,b,c")))
        achadas = correcao.correcoes(_editado(doc, 0, "a'b'c"))
        self.assertEqual([(c.antes, c.depois) for c in achadas], [(",", "'"), (",", "'")])

    def test_apagar_da_par_com_depois_vazio(self) -> None:
        doc = rico.de_pagina(_pagina(_texto("texto..com sujeira")))
        achadas = correcao.correcoes(_editado(doc, 0, "texto.com sujeira"))
        self.assertEqual([(c.antes, c.depois) for c in achadas], [(".", "")])

    def test_acrescentar_da_par_com_antes_vazio(self) -> None:
        doc = rico.de_pagina(_pagina(_texto("Nf")))
        achadas = correcao.correcoes(_editado(doc, 0, "Nf3"))
        self.assertEqual([(c.antes, c.depois) for c in achadas], [("", "3")])

    def test_o_motor_vem_da_pagina(self) -> None:
        doc = rico.de_pagina(_pagina(_texto("lido", procedencia="camada")))
        self.assertEqual(correcao.correcoes(_editado(doc, 0, "LIDO"))[0].motor, "camada")

    def test_a_troca_se_reconhece_da_insercao(self) -> None:
        doc = rico.de_pagina(_pagina(_texto("Nf")))
        self.assertFalse(correcao.correcoes(_editado(doc, 0, "Nf3"))[0].e_troca)
        doc = rico.de_pagina(_pagina(_texto("N,")))
        self.assertTrue(correcao.correcoes(_editado(doc, 0, "N'"))[0].e_troca)


class ForaDaContaTests(unittest.TestCase):
    def test_o_texto_novo_nao_conta_como_correcao(self) -> None:
        """Contá-lo inflaria a estatística de erro do OCR com o que alguém digitou por conta."""
        doc = rico.de_pagina(_pagina(_texto("lido")))
        com_novo = rico.DocumentoRico(
            corridas=(*doc.corridas, rico.Corrida(texto=" e mais isto")), origem=doc.origem
        )
        self.assertEqual(correcao.correcoes(com_novo), ())

    def test_o_diagrama_fica_de_fora(self) -> None:
        """A marca é referência, não leitura: apagá-la é editar estrutura, não corrigir o motor."""
        doc = rico.de_pagina(_pagina(BlocoDeDiagrama(indice=0, bbox=(0.0, 0.0, 5.0, 5.0))))
        self.assertEqual(correcao.correcoes(_editado(doc, 0, "")), ())

    def test_o_documento_sem_origem_nao_tem_correcao(self) -> None:
        self.assertEqual(correcao.correcoes(rico.de_texto("escrito do zero")), ())

    def test_bloco_fora_da_pagina_e_ignorado(self) -> None:
        """Só aparece em arquivo mexido por fora, e ali a resposta é ignorar, não estourar."""
        doc = rico.de_pagina(_pagina(_texto("lido")))
        torto = rico.DocumentoRico(
            corridas=(rico.Corrida(texto="?", bloco=99),), origem=doc.origem
        )
        self.assertEqual(correcao.correcoes(torto), ())


class ResumoTests(unittest.TestCase):
    def test_o_relatorio_agrupa_por_troca(self) -> None:
        doc = rico.de_pagina(_pagina(_texto("a,b,c,d")))
        dados = correcao.resumo(correcao.correcoes(_editado(doc, 0, "a'b'c'd")))
        self.assertEqual(dados["total"], 3)
        self.assertEqual(dados["trocas"], [{"antes": ",", "depois": "'", "vezes": 3}])

    def test_o_relatorio_conta_por_motor(self) -> None:
        doc = rico.de_pagina(_pagina(_texto("um", procedencia="glifo"), _texto("dois", procedencia="camada")))
        editado = _editado(_editado(doc, 0, "UM"), 1, "DOIS")
        self.assertEqual(correcao.resumo(correcao.correcoes(editado))["por_motor"], {"camada": 1, "glifo": 1})

    def test_as_trocas_saem_ordenadas_por_frequencia(self) -> None:
        doc = rico.de_pagina(_pagina(_texto("a,b,c.d")))
        dados = correcao.resumo(correcao.correcoes(_editado(doc, 0, "a'b'c'd")))
        self.assertEqual([t["vezes"] for t in dados["trocas"]], [2, 1])

    def test_o_empate_desempata_pelo_par(self) -> None:
        """Sem o desempate, dois relatórios do mesmo acervo deixam de ser comparáveis por `diff`."""
        doc = rico.de_pagina(_pagina(_texto("a,b.c")))
        dados = correcao.resumo(correcao.correcoes(_editado(doc, 0, "a'b'c")))
        self.assertEqual([(t["antes"], t["depois"]) for t in dados["trocas"]], [(",", "'"), (".", "'")])

    def test_o_resumo_vazio_nao_estoura(self) -> None:
        self.assertEqual(correcao.resumo(())["total"], 0)


def _modulo(relativo: str) -> Path:
    import chess_diagram_ocr

    return Path(chess_diagram_ocr.__file__).parent / relativo


def _codigo_sem_prosa(caminho: Path) -> str:
    """O módulo com docstrings fora -- o que **executa**, e não o que ele diz sobre si.

    Comentário some no `ast.parse`; docstring não, e ela é toda `Expr(Constant(str))`, esteja no
    topo do módulo ou logo abaixo de uma constante. Tirar as duas formas é o que separa "este módulo
    grava na base" de "este módulo explica que não grava na base".
    """
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        corpo = getattr(no, "body", None)
        if not isinstance(corpo, list):
            continue
        corpo[:] = [
            item
            for item in corpo
            if not (
                isinstance(item, ast.Expr)
                and isinstance(item.value, ast.Constant)
                and isinstance(item.value.value, str)
            )
        ]
    return ast.unparse(arvore)


class NaoRotulaTests(unittest.TestCase):
    """A cicatriz da S-180: 127 amostras rotuladas na classe errada, sem revisão no meio."""

    CAMINHOS = (
        "text/correcao.py",
        "text/arquivo.py",
        "text/rico.py",
        "cli/texto_correcoes.py",
    )

    PROIBIDOS = ("training_data", "char_to_folder", "salvar_amostra", "labels.csv")

    def test_o_editor_nao_escreve_na_base_de_treino(self) -> None:
        achados = []
        for relativo in self.CAMINHOS:
            codigo = _codigo_sem_prosa(_modulo(relativo))
            achados.extend(f"{relativo}: {termo}" for termo in self.PROIBIDOS if termo in codigo)
        self.assertEqual(achados, [], "O editor escreveu na base. Quem rotula é a S-212.")

    def test_a_varredura_nao_confunde_prosa_com_codigo(self) -> None:
        """A guarda da guarda: os módulos **falam** de `training_data` para dizer que não a tocam.

        Sem tirar a prosa, o teste acusaria justamente o comentário que promete o contrário -- e a
        saída fácil seria apagar a frase, que é o oposto do que se quer."""
        for relativo in self.CAMINHOS:
            with self.subTest(arquivo=relativo):
                bruto = _modulo(relativo).read_text(encoding="utf-8")
                if "training_data" in bruto:
                    self.assertNotIn("training_data", _codigo_sem_prosa(_modulo(relativo)))
                    return
        self.fail("Nenhum dos módulos menciona training_data: a varredura ficou sem caso.")


def _chaves(dados: object) -> set[str]:
    """Toda chave de todo objeto do JSON, em qualquer profundidade."""
    if isinstance(dados, dict):
        return set(dados) | {c for valor in dados.values() for c in _chaves(valor)}
    if isinstance(dados, list):
        return {c for item in dados for c in _chaves(item)}
    return set()


class SobrevivemAoArquivoTests(unittest.TestCase):
    """A correção não é gravada: ela é **derivada** dos dois lados que o arquivo guarda."""

    def test_o_par_antes_depois_sobrevive_ao_arquivo(self) -> None:
        doc = rico.de_pagina(_pagina(_texto("Black,s move")))
        editado = correcao.com_procedencia_humana(_editado(doc, 0, "Black's move"))
        with tempfile.TemporaryDirectory() as pasta:
            volta = arquivo.carregar(arquivo.gravar(Path(pasta) / "a.cvtxt", editado))
        self.assertEqual([(c.antes, c.depois) for c in correcao.correcoes(volta)], [(",", "'")])

    def test_nada_de_correcao_e_gravado_no_arquivo(self) -> None:
        """Gravá-la seria uma segunda fonte para a mesma pergunta -- e a que sairia do ar primeiro.

        A afirmação é sobre as **chaves** do JSON, e não sobre o texto: um documento cuja prosa
        contenha a palavra "antes" não pode reprovar o teste."""
        doc = rico.de_pagina(_pagina(_texto("Black,s")))
        editado = correcao.com_procedencia_humana(_editado(doc, 0, "Black's"))
        chaves = _chaves(arquivo.para_json(editado))
        self.assertEqual(chaves & {"correcao", "correcoes", "antes", "depois", "motor"}, set())


class ComandoTests(unittest.TestCase):
    def _arquivo(self, pasta: Path, nome: str, antes: str, depois: str) -> Path:
        doc = rico.de_pagina(_pagina(_texto(antes)))
        return arquivo.gravar(pasta / nome, correcao.com_procedencia_humana(_editado(doc, 0, depois)))

    def test_a_varredura_acha_os_cvtxt_da_pasta(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            self._arquivo(raiz, "um.cvtxt", "a,b", "a'b")
            self._arquivo(raiz / "dentro", "dois.cvtxt", "c,d", "c'd")
            (raiz / "outro.txt").write_text("nao é cvtxt", encoding="utf-8")
            achados = texto_correcoes.arquivos_de([raiz])
        self.assertEqual([c.name for c in achados], ["dois.cvtxt", "um.cvtxt"])

    def test_o_levantamento_soma_os_arquivos(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            self._arquivo(raiz, "um.cvtxt", "a,b", "a'b")
            self._arquivo(raiz, "dois.cvtxt", "c,d", "c'd")
            todas, por_arquivo = texto_correcoes.levantar(texto_correcoes.arquivos_de([raiz]))
        self.assertEqual(correcao.resumo(todas)["trocas"], [{"antes": ",", "depois": "'", "vezes": 2}])
        self.assertEqual(len(por_arquivo), 2)

    def test_arquivo_ilegivel_nao_interrompe_a_varredura(self) -> None:
        """Um `.cvtxt` corrompido no meio de trezentos não pode custar o levantamento inteiro."""
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            (raiz / "quebrado.cvtxt").write_text("nao é json", encoding="utf-8")
            self._arquivo(raiz, "bom.cvtxt", "a,b", "a'b")
            todas, por_arquivo = texto_correcoes.levantar(texto_correcoes.arquivos_de([raiz]))
        self.assertEqual(len(todas), 1)
        self.assertEqual([1 for linha in por_arquivo if "erro" in linha], [1])

    def test_o_resumo_impresso_traz_a_troca(self) -> None:
        linhas = texto_correcoes.linhas_do_resumo(
            correcao.resumo(
                (correcao.Correcao(bloco=0, antes=",", depois="'", motor="glifo"),)
            )
        )
        self.assertIn("1 correcao(oes) em 1 bloco(s)", linhas[0])
        self.assertTrue(any("1x" in linha for linha in linhas))

    def test_o_teto_de_trocas_avisa_o_que_ficou_de_fora(self) -> None:
        """Silêncio sobre o que foi cortado faria o relatório parecer completo sem ser."""
        muitas = tuple(
            correcao.Correcao(bloco=0, antes=str(i), depois="x", motor="glifo") for i in range(30)
        )
        linhas = texto_correcoes.linhas_do_resumo(correcao.resumo(muitas), teto=5)
        self.assertTrue(any("e mais 25 troca(s)" in linha for linha in linhas))

    def test_o_comando_sem_arquivo_nenhum_sai_em_paz(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            self.assertEqual(texto_correcoes.main([pasta]), 0)

    def test_o_json_traz_o_relatorio_inteiro(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            self._arquivo(raiz, "um.cvtxt", "a,b", "a'b")
            saida = raiz / "relatorio.json"
            self.assertEqual(texto_correcoes.main([str(raiz), "--json", str(saida)]), 0)
            dados = json.loads(saida.read_text(encoding="utf-8"))
        self.assertEqual(dados["total"], 1)
        self.assertEqual(dados["trocas"][0]["depois"], "'")
        self.assertEqual(len(dados["arquivos"]), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
