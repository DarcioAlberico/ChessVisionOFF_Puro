"""Precisão honesta, e o dado cru que não chega à tela (S-169).

**Dois defeitos com a mesma raiz: a tela mostrava o que a estrutura guarda.** A fila de revisão
escrevia prioridade `1623.8` — uma casa decimal num número que ninguém compara nesse detalhe, e
que por isso sugere uma diferença que não existe — e confiança `0.082`, num programa que fala de
confiança em porcentagem em todo outro lugar. A coluna "Lado" do Dataset publicava `w`, `b` e
`—`, as letras do CSV.

Cada formatador é afirmado com **valor típico, zero, negativo e ausente**, que são os quatro
casos em que um formatador erra. E há um teste para a regra que dá sentido a todos eles:
formatar é da apresentação, ordenar é do dado.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from chess_diagram_ocr.ui import strings
from chess_diagram_ocr.ui.formato import (
    AUSENTE,
    confianca,
    decimal,
    inteiro,
    lado_a_jogar,
    porcentagem,
    prioridade,
    texto_ou_ausente,
)


class InteiroTests(unittest.TestCase):
    def test_o_valor_tipico_ganha_separador_de_milhar(self) -> None:
        self.assertEqual(inteiro(1623.8), "1.624")
        self.assertEqual(inteiro(16234), "16.234")

    def test_zero_negativo_e_ausente(self) -> None:
        self.assertEqual(inteiro(0), "0")
        self.assertEqual(inteiro(-42.4), "-42")
        self.assertEqual(inteiro(None), AUSENTE)

    def test_o_separador_e_ponto_como_em_pt_br(self) -> None:
        """Vírgula de milhar é a convenção inglesa, e a janela é pt-BR."""
        self.assertNotIn(",", inteiro(1234567))
        self.assertEqual(inteiro(1234567), "1.234.567")


class PrioridadeTests(unittest.TestCase):
    """A casa decimal era ruído com aparência de exatidão."""

    def test_a_casa_decimal_sumiu(self) -> None:
        self.assertEqual(prioridade(1623.8), "1.624")
        self.assertNotIn(",", prioridade(1623.8))
        self.assertNotIn(".8", prioridade(1623.8))

    def test_dois_valores_que_pareciam_diferentes_agora_parecem_iguais(self) -> None:
        """E é isso que se quer: 1623,8 e 1623,7 **são** a mesma posição na fila."""
        self.assertEqual(prioridade(1623.8), prioridade(1623.7))

    def test_a_fila_vazia_nao_quebra(self) -> None:
        self.assertEqual(prioridade(None), AUSENTE)
        self.assertEqual(prioridade(0.0), "0")


class PorcentagemTests(unittest.TestCase):
    def test_o_valor_tipico(self) -> None:
        self.assertEqual(porcentagem(0.082), "8,2%")
        self.assertEqual(confianca(0.082), "8,2%")

    def test_a_virgula_decimal_e_a_de_pt_br(self) -> None:
        """O mesmo número com ponto num lugar e vírgula noutro é a S-04 aplicada a número."""
        self.assertIn(",", porcentagem(0.5))
        self.assertNotIn(".", porcentagem(0.5))

    def test_zero_um_e_ausente(self) -> None:
        self.assertEqual(porcentagem(0.0), "0,0%")
        self.assertEqual(porcentagem(1.0), "100,0%")
        self.assertEqual(porcentagem(None), AUSENTE)

    def test_negativo_nao_e_escondido(self) -> None:
        """Confiança negativa é bug de quem calculou; esconder faria a tela mentir por ele."""
        self.assertEqual(porcentagem(-0.05), "-5,0%")

    def test_o_numero_de_casas_e_do_chamador(self) -> None:
        self.assertEqual(porcentagem(0.08234, casas=0), "8%")
        self.assertEqual(porcentagem(0.08234, casas=2), "8,23%")


class DecimalTests(unittest.TestCase):
    """O número com casa decimal, pela mesma régua da porcentagem (S-910)."""

    def test_o_valor_tipico_sai_com_virgula(self) -> None:
        self.assertEqual(decimal(4.1, 2), "4,10")
        self.assertEqual(decimal(18.44, 1), "18,4")

    def test_zero_negativo_e_ausente(self) -> None:
        self.assertEqual(decimal(0.0, 1), "0,0")
        self.assertEqual(decimal(-0.25, 2), "-0,25")
        self.assertEqual(decimal(None, 2), AUSENTE)

    def test_sem_casas_nao_sobra_separador(self) -> None:
        self.assertEqual(decimal(62.4, 0), "62")

    def test_a_porcentagem_e_um_decimal_com_o_sinal(self) -> None:
        """Uma régua só: a porcentagem não reescreve a troca do separador."""
        self.assertEqual(porcentagem(0.08234, casas=2), decimal(8.234, 2) + "%")


_FONTE = Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr"

_SPEC_DECIMAL = re.compile(r"\.(\d+|\{\})[f%]$")
"""`:.2f`, `:>7.2%`, `:.{casas}f` -- toda especificação que escreve um separador decimal."""

EXCECOES_DECIMAL: dict[tuple[str, str], str] = {
    ("qt/painel_de_texto.py", "segundos"): (
        "a frase da leitura em lote já sai com vírgula pelo `.replace`; o arquivo estava em edição "
        "paralela quando a S-910 entrou, e a troca por `formato.decimal` ficou para depois"
    ),
}
"""(arquivo, expressão formatada) -> por que ela pode escrever o próprio separador.

Só entra aqui número que **não** é lido pelo usuário -- o que vai a arquivo, log ou JSON continua
com ponto, porque quem o lê é um programa -- ou uma pendência com nome."""


def _especificacao(no: ast.FormattedValue) -> str:
    """O texto da especificação de formato, com `{}` no lugar de um campo aninhado."""
    if not isinstance(no.format_spec, ast.JoinedStr):
        return ""
    return "".join(
        parte.value if isinstance(parte, ast.Constant) else "{}" for parte in no.format_spec.values
    )


def _decimais_escritos_a_mao() -> list[tuple[str, str, int]]:
    achados = []
    for pacote in ("ui", "qt"):
        for arquivo in sorted((_FONTE / pacote).rglob("*.py")):
            relativo = arquivo.relative_to(_FONTE).as_posix()
            if relativo == "ui/formato.py":
                continue
            arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                if isinstance(no, ast.FormattedValue) and _SPEC_DECIMAL.search(_especificacao(no)):
                    achados.append((relativo, ast.unparse(no.value), no.lineno))
    return achados


class GuardaDoSeparadorDecimalTests(unittest.TestCase):
    """Nenhum `:.Nf}` nem `:.N%}` em `ui/` e `qt/` fora de `formato` (S-910).

    Treze lugares trocavam o ponto pela vírgula à mão, e oito esqueciam -- `conf. mín. 0.93` ao
    lado de `8,2%` na mesma janela. A régua é uma só: `formato.decimal` e `formato.porcentagem`.
    """

    def test_ninguem_escreve_o_separador_decimal_a_mao(self) -> None:
        culpados = [
            f"{arquivo}:{linha} {{{expressao}:...}}"
            for arquivo, expressao, linha in _decimais_escritos_a_mao()
            if (arquivo, expressao) not in EXCECOES_DECIMAL
        ]
        self.assertEqual(culpados, [], "use formato.decimal / formato.porcentagem")

    def test_toda_excecao_ainda_existe(self) -> None:
        """Uma exceção que não acha mais nada é a guarda ficando vácua aos poucos."""
        presentes = {(arquivo, expressao) for arquivo, expressao, _ in _decimais_escritos_a_mao()}
        self.assertEqual(sorted(set(EXCECOES_DECIMAL) - presentes), [])

    def test_a_guarda_acha_o_que_procura(self) -> None:
        amostra = ast.parse('f"{x:.2f} {y:>7.2%} {z:.{casas}f} {w:.0f} {n:,} {p:>6}"')
        achados = [
            ast.unparse(no.value)
            for no in ast.walk(amostra)
            if isinstance(no, ast.FormattedValue) and _SPEC_DECIMAL.search(_especificacao(no))
        ]
        self.assertEqual(sorted(achados), ["w", "x", "y", "z"])


class LadoTests(unittest.TestCase):
    """O código do CSV não é para ser lido: ele é do arquivo."""

    def test_as_duas_letras_viram_os_nomes_da_interface(self) -> None:
        self.assertEqual(lado_a_jogar("w"), "Brancas")
        self.assertEqual(lado_a_jogar("b"), "Pretas")

    def test_a_ausencia_e_o_travessao(self) -> None:
        for cru in (None, "", "   "):
            with self.subTest(cru=cru):
                self.assertEqual(lado_a_jogar(cru), AUSENTE)

    def test_um_codigo_desconhecido_nao_vaza_para_a_tela(self) -> None:
        """Um `x` no CSV é dado corrompido; publicá-lo não ajuda ninguém a consertá-lo."""
        self.assertEqual(lado_a_jogar("x"), AUSENTE)

    def test_a_caixa_do_codigo_nao_importa(self) -> None:
        self.assertEqual(lado_a_jogar("W"), "Brancas")

    def test_o_rotulo_vem_do_vocabulario_e_nao_de_um_literal(self) -> None:
        """Existia escrito à mão em três lugares -- o rádio, a lista de partidas e a tabela."""
        self.assertEqual(lado_a_jogar("w"), strings.SIDE_LABELS["w"])


class TextoOuAusenteTests(unittest.TestCase):
    """Uma grafia de ausência, e não duas: célula vazia se lê como falha de carga."""

    def test_texto_passa(self) -> None:
        self.assertEqual(texto_ou_ausente("Karpov.pdf"), "Karpov.pdf")

    def test_vazio_none_e_espaco_dao_o_mesmo_travessao(self) -> None:
        for cru in (None, "", "   "):
            with self.subTest(cru=cru):
                self.assertEqual(texto_ou_ausente(cru), AUSENTE)

    def test_zero_e_um_valor_e_nao_uma_ausencia(self) -> None:
        """A página 0 existe. Tratá-la como falta é o erro clássico do `or`."""
        self.assertEqual(texto_ou_ausente(0), "0")


class OrdenarNaoEFormatarTests(unittest.TestCase):
    """A regra que dá sentido ao módulo inteiro (S-169).

    Ordenar pela string formatada põe `1.000` antes de `999` e `9,9%` antes de `82,0%`. O
    formatador devolve **texto**, e o texto não entra no caminho de comparação -- é essa a
    separação, e é ela que o teste trava.
    """

    def test_ordenar_pelo_texto_da_prioridade_estaria_errado(self) -> None:
        valores = [999.0, 1000.0, 82.0]
        por_texto = sorted(valores, key=prioridade)
        por_valor = sorted(valores)
        self.assertNotEqual(por_texto, por_valor, "o exemplo deixou de demonstrar o defeito")

    def test_ordenar_pelo_texto_da_porcentagem_estaria_errado(self) -> None:
        valores = [0.099, 0.82, 0.5]
        self.assertNotEqual(sorted(valores, key=porcentagem), sorted(valores))

    def test_os_paineis_ordenam_antes_de_formatar(self) -> None:
        """A fila é ordenada por `ReviewQueue.sort`, sobre o número -- e só depois é escrita."""
        from pathlib import Path

        fonte = (Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr" / "qt" / "painel_de_revisao.py")
        texto_do_painel = fonte.read_text(encoding="utf-8")
        self.assertIn("self.queue.sort()", texto_do_painel)
        self.assertIn("formato.prioridade(item.priority)", texto_do_painel)


class SemDadoCruNaTelaTests(unittest.TestCase):
    """A varredura: os dois painéis passaram a formatar, e o literal antigo não voltou."""

    def _fonte(self, nome: str) -> str:
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr" / "qt"
        return (raiz / nome).read_text(encoding="utf-8")

    def test_a_fila_nao_escreve_mais_a_casa_decimal(self) -> None:
        painel = self._fonte("painel_de_revisao.py")
        self.assertNotIn('f"{item.priority:.1f}"', painel)
        self.assertNotIn('f"{item.min_confidence:.3f}"', painel)

    def test_o_dataset_nao_publica_mais_a_letra_do_csv(self) -> None:
        """O arquivo mudou na S-503: quem monta a linha é `ui/resumo_do_dataset.celulas`, que
        os dois frontends chamam. A guarda seguiu o código -- deixá-la apontando para o painel
        do Tk a tornaria vácua, porque lá não há mais nenhuma célula sendo montada."""
        montagem = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "chess_diagram_ocr"
            / "ui"
            / "resumo_do_dataset.py"
        ).read_text(encoding="utf-8")
        self.assertIn("formato.lado_a_jogar(row.side_to_move)", montagem)
        self.assertNotIn('row.side_to_move or "—"', montagem)
        self.assertNotIn('row.side_to_move or "—"', self._fonte("painel_do_dataset.py"))


if __name__ == "__main__":
    unittest.main()
