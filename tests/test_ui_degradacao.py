"""O contrato de degradação da aparência: cair um degrau, registrar uma vez, nunca levantar (S-234).

`ui/theme.py` fixou o contrato na S-53 -- *"tema é aparência, e aparência não derruba ferramenta"*
-- e a Fase 35 acrescentou eixos, cada um um modo de falha novo: pele, densidade, ícone e conjunto
de peças. Todos acontecem na abertura, que é o pior momento: uma exceção ali não degrada nada, ela
apaga o programa antes de ele existir.

**Este arquivo existiu até o corte do Tk e morreu com ele** (S-506): a versão antiga abria uma
raiz `Tk` para provar que as três peles montavam o cromo, e saiu inteira -- levando junto as
partes que não precisavam de janela nenhuma. `degradacao.QUEDAS` ficou um mês sem leitor, e é o
achado da triagem da S-511: a linha `pasta_de_pecas` apontava para o `board_render.PieceImages`,
que não existia mais, e a queda do Qt acontecia em silêncio. O que aqui se trava é o contrato
inteiro, e não a ausência de exceção: **cair no degrau certo**, **avisar**, e avisar **uma vez**.
"""

from __future__ import annotations

import importlib
import logging
import unittest
from pathlib import Path

from qt_app import MOTIVO, TEM_PYQT

from chess_diagram_ocr.ui import conjuntos, degradacao, icones, pele

if TEM_PYQT:
    from chess_diagram_ocr.qt import tabuleiro as qt_tabuleiro

PRETO = "#101010"


def _dono(caminho: str) -> object:
    """Resolve o `dono` declarado numa `Queda`: `pele.valida` é de `ui/`, `qt/tabuleiro.x` é de `qt/`."""
    modulo, nome = caminho.rsplit(".", 1)
    pacote = "chess_diagram_ocr.ui"
    if modulo.startswith("qt/"):
        pacote, modulo = "chess_diagram_ocr.qt", modulo[3:]
    return getattr(importlib.import_module(f"{pacote}.{modulo}"), nome)


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
        quedas: dict[str, tuple[logging.Logger, object, object]] = {
            "pele": (pele.logger, lambda: pele.valida("pele_que_nao_existe"), pele.CLASSICA),
            # A fita sugere compacta: a queda tem de dar **confortável** mesmo assim, que é o que
            # a tabela declara -- quem escreveu um nome errado não pediu nada apertado.
            "densidade": (
                pele.logger,
                lambda: pele.densidade_em_vigor(pele.registrada(pele.FITA), "folgada", ambiente={}),
                pele.CONFORTAVEL,
            ),
            "icone": (icones.logger, lambda: icones.imagem("icone_que_nao_existe", 24, PRETO), None),
            "desenho": (icones.logger, lambda: icones.imagem("salvar", 24, "isto_nao_e_cor"), None),
            "conjunto": (conjuntos.logger, lambda: conjuntos.valida("conjunto_que_nao_existe"), conjuntos.PADRAO),
        }
        if TEM_PYQT:
            quedas["pasta_de_pecas"] = (
                qt_tabuleiro.logger,
                lambda: qt_tabuleiro.carregar_pecas(Path("pasta") / "que" / "nao" / "existe"),
                {},
            )
        return quedas

    def test_toda_queda_declarada_tem_reproducao(self) -> None:
        """**A tabela e o teste não podem divergir**, e a divergência seria silenciosa: uma linha
        nova em `QUEDAS` sem caso aqui viraria uma promessa que ninguém confere."""
        declaradas = {registro.chave for registro in degradacao.QUEDAS}
        if not TEM_PYQT:
            declaradas.discard("pasta_de_pecas")
        self.assertEqual(declaradas, set(self._quedas()))
        self.assertEqual(len(degradacao.QUEDAS), len({registro.chave for registro in degradacao.QUEDAS}), "chave repetida")

    def test_todo_dono_declarado_existe_e_e_chamavel(self) -> None:
        """A linha que o corte deixou apontando para `board_render.PieceImages`, que não existia mais:
        um dono que não resolve é a tabela descrevendo um programa que não é este."""
        for registro in degradacao.QUEDAS:
            if registro.dono.startswith("qt/") and not TEM_PYQT:
                continue
            with self.subTest(queda=registro.chave, dono=registro.dono):
                self.assertTrue(callable(_dono(registro.dono)))

    def test_as_quedas(self) -> None:
        """Cada falha cai no degrau declarado, **avisa**, e não levanta. As três coisas juntas."""
        for chave, (registrador, fazer, esperado) in self._quedas().items():
            declarada = next(registro for registro in degradacao.QUEDAS if registro.chave == chave)
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
            "conjunto": ("conjunto_que_nao_existe", conjuntos.logger, lambda: conjuntos.valida("conjunto_que_nao_existe")),
            "icone": ("icone_que_nao_existe", icones.logger, lambda: icones.imagem("icone_que_nao_existe", 24, PRETO)),
        }
        if TEM_PYQT:
            casos["pasta_de_pecas"] = (
                "nao",
                qt_tabuleiro.logger,
                lambda: qt_tabuleiro.carregar_pecas(Path("pasta") / "que" / "nao" / "existe"),
            )
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
        """A troca de pele refaz o cromo inteiro, e o que falta lá continua faltando -- é por isso
        que `qt/janela.py` chama `esquecer_avisos` ao trocar de pele, ao lado de limpar o cache de
        ícones."""
        icones.imagem("icone_que_nao_existe", 24, PRETO)
        self.assertEqual(1, degradacao.avisos_dados())
        degradacao.esquecer_avisos()
        self.assertEqual(0, degradacao.avisos_dados())
        with self.assertLogs(icones.logger, level="WARNING"):
            icones.imagem("icone_que_nao_existe", 24, PRETO)


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class PastaDePecasTests(unittest.TestCase):
    """A linha da tabela que o corte deixou sem dono, agora com dono e com voz."""

    def setUp(self) -> None:
        degradacao.esquecer_avisos()
        self.addCleanup(degradacao.esquecer_avisos)

    def test_pasta_ausente_cai_no_glifo_e_avisa_uma_vez(self) -> None:
        pasta = Path("pasta") / "que" / "nao" / "existe"
        with self.assertLogs(qt_tabuleiro.logger, level="WARNING") as registro:
            self.assertEqual({}, qt_tabuleiro.carregar_pecas(pasta))
            self.assertEqual({}, qt_tabuleiro.carregar_pecas(pasta))
        self.assertEqual(1, len(registro.output), "a mesma pasta avisou duas vezes")
        self.assertIn(str(pasta), registro.output[0])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
