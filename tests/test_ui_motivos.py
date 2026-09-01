"""Todo controle que pode ficar cinza diz por quê (S-165, fechando a S-32).

`ui/tooltip.py` nasceu na S-32 com um propósito escrito no docstring: **"um botão cinza sem
explicação é pior que um botão ausente"** -- ausente, a pessoa procura outro caminho; cinza, ela
conclui que o programa está quebrado. A S-32 cobriu três botões. Quando esta varredura foi escrita,
havia **13 controles desabiláveis sem tooltip nenhum** -- o cancelar da Galeria, o da fila, o de
exportação, o "Analisar posição", o campo do número do lance, o "Treinar modelo".

A regra passou a ser verificada em vez de lembrada: quem escrever `state=tk.DISABLED` num controle
novo falha aqui até dizer o motivo.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

ARQUIVOS_DE_UI = sorted((RAIZ / "src" / "chess_diagram_ocr" / "ui").glob("*.py")) + sorted(
    (RAIZ / "src" / "chess_diagram_ocr" / "qt").glob("*.py")
)

SEM_MOTIVO: dict[tuple[str, str], str] = {}
"""Os controles desligados que **não** precisam de motivo, e por quê -- uma linha cada.

**Vazia desde o corte do Tk (S-506), e a razão é do toolkit.** Ela guardava dois `tk.Text` de
leitura: no Tk, `state=DISABLED` era ao mesmo tempo "controle desligado" e "texto não editável",
e a varredura não distinguia os dois. O Qt separa: texto de leitura é `setReadOnly(True)` e
continua com foco e seleção; controle desligado é `setEnabled(False)`. A ambiguidade que a lista
existia para desfazer deixou de existir, e obrigar tooltip num parágrafo era ruído com aparência
de rigor.

A lista continua aqui porque a distinção pode voltar a fazer falta. Uma linha nova precisa vir com
a razão junto."""


def _desabilitaveis(caminho: Path) -> set[str]:
    """Os widgets que aparecem num `configure(state=...DISABLED...)` neste arquivo.

    O `configure` e não a construção: um controle que **nasce** desabilitado e nunca acende é raro,
    e o que interessa é o widget cujo estado varia -- é dele que a pessoa pergunta "por que está
    cinza agora?".
    """
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    achados: set[str] = set()
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call) or not isinstance(no.func, ast.Attribute):
            continue
        if no.func.attr not in ("configure", "config"):
            continue
        texto = ast.unparse(no)
        if "state=" in texto and ("DISABLED" in texto or "disabled" in texto):
            achados.add(ast.unparse(no.func.value))
    return achados


def _texto_do_tooltip(fonte: str, alvo: str) -> str | None:
    """O texto do `Tooltip` daquele widget, ou `None` quando nao ha um.

    Procura a partir da chamada, e nao da primeira mencao ao nome do widget: entre a linha que o
    cria e a que explica o motivo ha o `pack`, os `bind` e as vezes 40 linhas de outro assunto.
    """
    for abertura in (f"Tooltip({alvo}", "Tooltip(" + chr(10) + " " * 12 + alvo + ","):
        posicao = fonte.find(abertura)
        if posicao >= 0:
            return fonte[posicao : posicao + 700]
    return None


class MotivoEscritoTests(unittest.TestCase):
    def test_todo_controle_desabilitavel_tem_tooltip(self) -> None:
        faltando = []
        for caminho in ARQUIVOS_DE_UI:
            fonte = caminho.read_text(encoding="utf-8")
            for alvo in sorted(_desabilitaveis(caminho)):
                if (caminho.name, alvo) in SEM_MOTIVO:
                    continue
                if _texto_do_tooltip(fonte, alvo) is not None:
                    continue
                faltando.append(f"{caminho.name}: {alvo}")
        self.assertEqual(
            faltando,
            [],
            "Controle que fica cinza sem dizer por quê. Ou ele ganha `Tooltip(...)` com o motivo, "
            "ou entra em SEM_MOTIVO explicando por que não é um controle.",
        )

    def test_a_lista_de_excecoes_nao_guarda_widget_que_nao_existe_mais(self) -> None:
        """Exceção que sobrevive ao widget que a justificava vira permissão em branco (S-112)."""
        reais = {(caminho.name, alvo) for caminho in ARQUIVOS_DE_UI for alvo in _desabilitaveis(caminho)}
        self.assertEqual(sorted(set(SEM_MOTIVO) - reais), [])

    def test_cada_excecao_diz_por_que(self) -> None:
        for chave, motivo in SEM_MOTIVO.items():
            self.assertGreater(len(motivo), 60, f"{chave} está na lista sem justificativa")

    def test_o_motivo_fala_do_estado_e_nao_so_do_botao(self) -> None:
        """Um tooltip que repete o rótulo não fecha a S-32: o que falta saber é **por que agora**.

        A checagem é grosseira de propósito -- procura as palavras que descrevem estado ("fica
        cinza", "só fica ativo", "durante", "sem ...") no texto de cada tooltip de controle
        desabilitável. Ela não julga a redação; ela impede o tooltip decorativo.
        """
        pistas = ("cinza", "só fica ativo", "durante", "enquanto", "sem ", "precisa de", "desabilitado")
        fracos = []
        for caminho in ARQUIVOS_DE_UI:
            fonte = caminho.read_text(encoding="utf-8")
            for alvo in sorted(_desabilitaveis(caminho)):
                if (caminho.name, alvo) in SEM_MOTIVO:
                    continue
                texto = _texto_do_tooltip(fonte, alvo)
                if texto is None:
                    continue
                # O motivo pode ser **escrito na hora**: os dois botões de leitura externa trocam
                # o texto do tooltip pelo `disabled_reason()` da configuração (S-32/S-66), que diz
                # qual das situações é -- "não configurado" e "configurado e desligado" são
                # diferentes, e uma frase fixa não daria conta das duas.
                if "disabled_reason" in fonte:
                    continue
                if not any(pista in texto.casefold() for pista in pistas):
                    fracos.append(f"{caminho.name}: {alvo}")
        self.assertEqual(fracos, [], "tooltip que não diz quando o controle fica indisponível")


if __name__ == "__main__":
    unittest.main()
