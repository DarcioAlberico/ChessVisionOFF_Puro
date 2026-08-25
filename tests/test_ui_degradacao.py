"""O contrato de degradação da aparência: cair um degrau, registrar uma vez, nunca levantar (S-234).

`ui/theme.py` fixou o contrato na S-53 — *"tema é aparência, e aparência não derruba ferramenta"* —
e `apply_theme` o cumpre há tempo. **A Fase 35 acrescentou quatro eixos, e cada eixo é um modo de
falha novo:** pele, densidade, ícone e conjunto de peças. Os quatro acontecem na abertura, que é o
pior momento — uma exceção ali não degrada nada, ela apaga o programa antes de ele existir.

O que estes testes travam é o contrato inteiro, e não a ausência de exceção: **cair no degrau
certo**, **avisar**, e avisar **uma vez** — porque um aviso por widget é um log que ninguém lê, e
uma queda silenciosa é "o programa está estranho hoje".
"""

from __future__ import annotations

import logging
import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from tk_root import raiz

from chess_diagram_ocr.ui import board_render, conjuntos, degradacao, icones, pele, theme

PRETO = "#101010"


class TabelaDasQuedasTests(unittest.TestCase):
    """As seis linhas da tabela da SPEC_APARENCIA, exercitadas uma a uma.

    A tabela virou dado (`degradacao.QUEDAS`) pela mesma razão de `comandos.CATALOGO`: enquanto ela
    foi prosa em quatro docstrings, "as seis quedas funcionam" era uma frase.
    """

    def setUp(self) -> None:
        degradacao.esquecer_avisos()
        self.addCleanup(degradacao.esquecer_avisos)

    def _quedas(self) -> dict[str, tuple[logging.Logger, object, object]]:
        """`chave → (logger, o que fazer, o que tem de sair)`. Uma entrada por linha da tabela."""
        return {
            "pele": (pele.logger, lambda: pele.valida("pele_que_nao_existe"), pele.CLASSICA),
            "densidade": (
                pele.logger,
                lambda: pele.densidade_em_vigor(pele.registrada(pele.FITA), "folgada", ambiente={}),
                pele.CONFORTAVEL,
            ),
            # A fita sugere compacta: a queda tem de dar **confortável** mesmo assim, que é o que
            # a tabela declara -- quem escreveu um nome errado não pediu nada apertado.
            "icone": (icones.logger, lambda: icones.imagem("icone_que_nao_existe", 24, PRETO), None),
            "desenho": (icones.logger, lambda: icones.imagem("salvar", 24, "isto_nao_e_cor"), None),
            "pasta_de_pecas": (
                board_render.logger,
                lambda: board_render.PieceImages(Path("pasta") / "que" / "nao" / "existe").icon("K", 24),
                None,
            ),
            "conjunto": (conjuntos.logger, lambda: conjuntos.valida("conjunto_que_nao_existe"), conjuntos.PADRAO),
        }

    def test_toda_queda_declarada_tem_reproducao(self) -> None:
        """**A tabela e o teste não podem divergir**, e a divergência seria silenciosa: uma linha
        nova em `QUEDAS` sem caso aqui viraria uma promessa que ninguém confere."""
        self.assertEqual({registro.chave for registro in degradacao.QUEDAS}, set(self._quedas()))
        self.assertEqual(len(degradacao.QUEDAS), len(degradacao.por_chave), "chave repetida na tabela")

    def test_as_seis_quedas(self) -> None:
        """Cada falha cai no degrau declarado, **avisa**, e não levanta. As três coisas juntas."""
        for chave, (registrador, fazer, esperado) in self._quedas().items():
            declarada = degradacao.por_chave[chave]
            with self.subTest(queda=chave, cai_em=declarada.queda):
                degradacao.esquecer_avisos()
                with self.assertLogs(registrador, level="WARNING") as registro:
                    obtido = fazer()
                self.assertEqual(esperado, obtido, f"{chave}: não caiu em {declarada.queda}")
                self.assertTrue("\n".join(registro.output).strip(), f"{chave}: caiu em silêncio")

    def test_a_falha_nomeia_o_valor_que_a_causou(self) -> None:
        """Metade do valor do aviso. Sem o nome, quem escreveu `CVOFF_SKIN=fita` numa versão sem
        fita conclui que a variável não é lida (S-221)."""
        casos = {
            "pele": ("pele_que_nao_existe", pele.logger, lambda: pele.valida("pele_que_nao_existe")),
            "conjunto": (
                "conjunto_que_nao_existe",
                conjuntos.logger,
                lambda: conjuntos.valida("conjunto_que_nao_existe"),
            ),
            "icone": (
                "icone_que_nao_existe",
                icones.logger,
                lambda: icones.imagem("icone_que_nao_existe", 24, PRETO),
            ),
        }
        for chave, (nome, registrador, fazer) in casos.items():
            with self.subTest(queda=chave):
                degradacao.esquecer_avisos()
                with self.assertLogs(registrador, level="WARNING") as registro:
                    fazer()
                self.assertIn(nome, "\n".join(registro.output))

    def test_nenhuma_queda_levanta(self) -> None:
        """A regra 4 numa linha: **aparência não derruba ferramenta.**"""
        for chave, (_registrador, fazer, _esperado) in self._quedas().items():
            with self.subTest(queda=chave):
                try:
                    fazer()
                except Exception as exc:  # noqa: BLE001 - é a falha que o teste existe para pegar
                    self.fail(f"{chave} levantou {type(exc).__name__}: {exc}")


class AvisoUmaVezTests(unittest.TestCase):
    """O "registra uma vez" do contrato, que é a metade que a fita torna cara."""

    def setUp(self) -> None:
        degradacao.esquecer_avisos()
        self.addCleanup(degradacao.esquecer_avisos)

    def test_o_aviso_sai_uma_vez_so(self) -> None:
        """**Uma vez por nome, e não uma por botão.**

        A fita desenha dezessete botões e os redesenha a cada troca de pele e a cada mudança de
        densidade. Sem esta guarda, um ícone com nome errado escreve dezessete linhas iguais por
        remontagem -- e um log que se repete assim deixa de ser lido, que é o mesmo custo de não
        registrar nada.
        """
        with self.assertLogs(icones.logger, level="WARNING") as registro:
            for _ in range(17):
                self.assertIsNone(icones.imagem("icone_que_nao_existe", 24, PRETO))
        self.assertEqual(1, len(registro.output), "o aviso saiu mais de uma vez")

    def test_um_nome_novo_nao_e_calado(self) -> None:
        """A chave carrega o **valor**, e não só o assunto: o segundo nome é informação nova."""
        icones.imagem("primeiro_que_falta", 24, PRETO)
        with self.assertLogs(icones.logger, level="WARNING") as registro:
            icones.imagem("segundo_que_falta", 24, PRETO)
        self.assertIn("segundo_que_falta", "\n".join(registro.output))
        self.assertEqual(2, degradacao.avisos_dados())

    def test_esquecer_avisos_devolve_a_voz(self) -> None:
        """A troca de pele refaz o cromo inteiro, e o que falta lá continua faltando."""
        icones.imagem("icone_que_nao_existe", 24, PRETO)
        self.assertEqual(1, degradacao.avisos_dados())
        degradacao.esquecer_avisos()
        self.assertEqual(0, degradacao.avisos_dados())
        with self.assertLogs(icones.logger, level="WARNING"):
            icones.imagem("icone_que_nao_existe", 24, PRETO)


class AsTresPelesAbremTests(unittest.TestCase):
    """A afirmação que o item existe para transformar de esperança em teste."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        degradacao.esquecer_avisos()
        self.addCleanup(degradacao.esquecer_avisos)
        # A prova troca o tema (cada pele sugere o seu). Devolver a janela ao estado de antes
        # evita que a ordem dos testes decida a aparência dos vizinhos.
        self.addCleanup(lambda: theme.apply_theme(self.root))

    def test_o_selftest_roda_nas_tres_peles(self) -> None:
        """`provar_as_peles` é o passo que o `--selftest` ganhou, e é ele que roda aqui.

        **Chamar `app_tkinter.selftest` inteiro seria outro teste** -- ele pede checkpoint e PDF, e
        criaria uma segunda raiz Tk no processo, que é exatamente o que `tests/tk_root.py`
        documenta como não confiável no Windows. O laço mora em `ui/degradacao.py` para que a
        suíte possa fazer a mesma pergunta com a raiz compartilhada.
        """
        self.assertEqual([], degradacao.provar_as_peles(self.root))

    def test_cada_pele_monta_o_cromo_dela(self) -> None:
        for registro in pele.PELES:
            with self.subTest(pele=registro.nome):
                self.assertEqual([], degradacao.abrir_cromo_de_prova(self.root, registro.nome))

    def test_pele_desconhecida_volta_como_problema_e_nao_como_excecao(self) -> None:
        """Um auto-teste que estoura ao dizer que algo estourou não serve."""
        problemas = degradacao.abrir_cromo_de_prova(self.root, "pele_que_nao_existe")
        self.assertEqual(1, len(problemas))
        self.assertIn("pele_que_nao_existe", problemas[0])

    def test_as_tres_peles_abrem_sem_ttkbootstrap(self) -> None:
        """**O contrato original da S-53, agora medido nas três peles.**

        `sys.modules["ttkbootstrap"] = None` faz o `import` levantar `ImportError`, que é o que
        acontece num checkout sem o extra ou num bundle que não o incluiu. `apply_theme` cai no
        `ttk` puro e diz isso no log; o cromo das três continua montando.
        """
        with patch.dict(sys.modules, {"ttkbootstrap": None}):
            self.assertEqual("ttk", theme.apply_theme(self.root))
            self.assertEqual([], degradacao.provar_as_peles(self.root))

    def test_nenhum_caminho_de_aparencia_aparece_num_traceback(self) -> None:
        """A combinação inteira: pele x densidade, com o tema recusado por nome inválido.

        É a linha final do critério de aceite -- *"nenhum caminho de aparência aparece num
        `traceback` de abertura, em nenhuma combinação"* --, e ela é barata porque as peças já são
        puras: o que varia aqui é só o que a montagem lê.
        """
        for registro in pele.PELES:
            for densidade in (*pele.DENSIDADES, "densidade_que_nao_existe"):
                with self.subTest(pele=registro.nome, densidade=densidade):
                    with patch.dict("os.environ", {pele.DENSIDADE_ENV: densidade}):
                        theme.apply_theme(self.root, "tema_que_nao_existe")
                        self.assertEqual([], degradacao.abrir_cromo_de_prova(self.root, registro.nome))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
