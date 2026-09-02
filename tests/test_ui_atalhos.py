"""As teclas declaradas uma vez, e o que as duas tabelas dividem (S-161/S-244/S-259/S-294/S-511).

`ui/atalhos.py` tem duas tabelas: `ATALHOS`, as teclas **da janela**, e `TECLAS_DO_EDITOR`, as que
só existem dentro do editor de texto. Quatro sequências estão nas duas, e `SOBREPOSICOES_NO_EDITOR`
diz, de cada uma, quem fica com ela. Até o corte do Tk quem cobrava essa tabela era
`test_ui_atalhos_destino`, que morreu junto com o `Text.bind` que ele exercitava -- e o módulo
ficou um mês sem nenhum teste puro, com as três constantes da sobreposição sem leitor (S-511).

O que se afirma aqui não precisa de janela: a sobreposição declarada é consistente com
`ACOES_PROPRIAS` nos dois sentidos, toda tecla do editor tem comando na aba, a régua de cessão da
S-294 responde o que a medição pediu, e `conferir_dono` recusa a promessa vazia da S-244.
"""

from __future__ import annotations

import unittest
from unittest import mock

from chess_diagram_ocr.ui import atalhos, texto_declarado


def _acoes_do_editor(sequencia: str) -> list[str]:
    return [acao for acao, tecla in atalhos.TECLAS_DO_EDITOR.items() if tecla == sequencia]


class SobreposicaoTests(unittest.TestCase):
    """As teclas que estão nas duas tabelas, e de qual dos dois tipos cada uma é."""

    def test_toda_tecla_nas_duas_tabelas_tem_sobreposicao_declarada(self) -> None:
        """A tabela e as duas listas não podem divergir: uma tecla do editor que entre em `ATALHOS`
        sem linha aqui é exatamente "a sobreposição seguinte" que a tabela existe para impedir."""
        nas_duas = {tecla for tecla in atalhos.TECLAS_DO_EDITOR.values() if atalhos.acao_de(tecla)}
        self.assertEqual(nas_duas, set(atalhos.SOBREPOSICOES_NO_EDITOR))
        for tecla in nas_duas:
            with self.subTest(tecla=tecla):
                self.assertIn(atalhos.sobreposicao(tecla), (atalhos.CEDIDA_PELA_GUARDA, atalhos.GANHA_DO_TK))

    def test_cedida_pela_guarda_e_outra_acao_que_o_painel_nao_declara(self) -> None:
        """`Ctrl+R` é "ler esta página" na janela e "alinhar à direita" no editor. O sinal de que a
        guarda cede é a ação do editor **não** estar em `ACOES_PROPRIAS`: se estivesse, a janela
        entregaria a tecla ao painel pelo outro caminho, e ela teria dois donos."""
        for tecla, tipo in atalhos.SOBREPOSICOES_NO_EDITOR.items():
            if tipo != atalhos.CEDIDA_PELA_GUARDA:
                continue
            with self.subTest(tecla=tecla):
                (do_editor,) = _acoes_do_editor(tecla)
                self.assertNotEqual(do_editor, atalhos.acao_de(tecla))
                self.assertNotIn(do_editor, texto_declarado.ACOES_PROPRIAS)

    def test_ganha_do_tk_e_a_mesma_acao_e_o_painel_a_declara(self) -> None:
        """`Ctrl+H` é "substituir" nas duas tabelas. A janela ganha, e a guarda entrega a ação ao
        painel por `acoes_proprias` -- então a ação **tem** de estar lá, senão a tecla morre."""
        for tecla, tipo in atalhos.SOBREPOSICOES_NO_EDITOR.items():
            if tipo != atalhos.GANHA_DO_TK:
                continue
            with self.subTest(tecla=tecla):
                (do_editor,) = _acoes_do_editor(tecla)
                self.assertEqual(do_editor, atalhos.acao_de(tecla))
                self.assertIn(do_editor, texto_declarado.ACOES_PROPRIAS)

    def test_tecla_so_do_editor_nao_tem_sobreposicao(self) -> None:
        self.assertIsNone(atalhos.sobreposicao(atalhos.TECLAS_DO_EDITOR["negrito"]))

    def test_sobreposicao_nova_sem_linha_reprova_nomeando_a_tecla(self) -> None:
        """É o que faz a tabela valer na montagem do painel, e não só aqui."""
        with mock.patch.dict(atalhos.SOBREPOSICOES_NO_EDITOR, {}, clear=True):
            with self.assertRaises(KeyError) as erro:
                atalhos.sobreposicao("<Control-r>")
        self.assertIn("<Control-r>", str(erro.exception))

    def test_as_cedidas_ao_editor_excluem_a_que_a_janela_ganha(self) -> None:
        cedidas = atalhos.teclas_cedidas_ao_editor()
        self.assertIn(atalhos.TECLAS_DO_EDITOR["negrito"], cedidas, "tecla só do editor é do editor")
        self.assertIn("<Control-r>", cedidas, "cedida pela guarda é do editor")
        self.assertNotIn("<Control-h>", cedidas, "a que a janela ganha não é reclamada pelo editor")
        ganhas = [t for t, tipo in atalhos.SOBREPOSICOES_NO_EDITOR.items() if tipo == atalhos.GANHA_DO_TK]
        self.assertEqual(len(cedidas), len(set(atalhos.TECLAS_DO_EDITOR.values())) - len(ganhas))


class TabelaDoEditorTests(unittest.TestCase):
    def test_toda_tecla_do_editor_tem_comando_na_aba(self) -> None:
        """A tecla dispara `PainelDeTexto.executar(acao)`, e `executar` lê `COMANDOS_DA_ABA`: uma
        tecla para um comando que a aba não liga seria a promessa vazia com outro nome."""
        for acao in atalhos.TECLAS_DO_EDITOR:
            with self.subTest(acao=acao):
                self.assertIn(acao, texto_declarado.COMANDOS_DA_ABA)

    def test_nenhuma_tecla_do_editor_e_declarada_duas_vezes(self) -> None:
        teclas = list(atalhos.TECLAS_DO_EDITOR.values())
        self.assertEqual(len(teclas), len(set(teclas)))


class CessaoTests(unittest.TestCase):
    """A régua da S-294: a guarda cede o que o campo **usa**, e não tudo."""

    def test_a_seta_e_do_campo(self) -> None:
        self.assertTrue(atalhos.cede_a_sequencia("<Left>", e_campo=True, e_multilinha=False))

    def test_o_ctrl_s_nao_e_de_campo_nenhum(self) -> None:
        """O defeito medido: com o cursor no campo de FEN, `Ctrl+S` não salvava."""
        self.assertFalse(atalhos.cede_a_sequencia("<Control-s>", e_campo=True, e_multilinha=True))

    def test_pgup_so_e_de_quem_rola(self) -> None:
        self.assertFalse(atalhos.cede_a_sequencia("<Prior>", e_campo=True, e_multilinha=False))
        self.assertTrue(atalhos.cede_a_sequencia("<Prior>", e_campo=True, e_multilinha=True))

    def test_fora_de_campo_nada_e_cedido(self) -> None:
        self.assertFalse(atalhos.cede_a_sequencia("<Left>", e_campo=False, e_multilinha=False))

    def test_sem_sequencia_o_lado_seguro_e_ceder(self) -> None:
        self.assertTrue(atalhos.cede_a_sequencia("", e_campo=True, e_multilinha=False))


class _Dono:
    def __init__(self, declara: frozenset[str], atende: dict[str, object]) -> None:
        self._declara = declara
        self._atende = atende

    def acoes_proprias(self) -> frozenset[str]:
        return self._declara

    def atender(self, acao: str):  # noqa: ANN201 - assinatura do protocolo
        return self._atende.get(acao)


class DonoDeAcoesTests(unittest.TestCase):
    """A promessa vazia que a S-244 proíbe: declarar uma ação e não a atender come a tecla."""

    def test_declarar_e_atender_passa(self) -> None:
        atalhos.conferir_dono(_Dono(frozenset({"salvar"}), {"salvar": lambda: None}), "painel de mentira")

    def test_declarar_sem_atender_levanta_nomeando_a_acao(self) -> None:
        with self.assertRaises(KeyError) as erro:
            atalhos.conferir_dono(_Dono(frozenset({"salvar", "achar"}), {"salvar": lambda: None}), "painel de mentira")
        self.assertIn("achar", str(erro.exception))
        self.assertIn("painel de mentira", str(erro.exception))

    def test_o_painel_que_declara_e_reconhecido_pelo_protocolo(self) -> None:
        self.assertIsInstance(_Dono(frozenset(), {}), atalhos.DonoDeAcoes)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
