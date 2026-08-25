"""Desfazer e refazer a edição do tabuleiro: uma pilha de **posições** (S-229).

**A função que faltava.** Quando este módulo foi escrito, `grep -rn 'undo' src/` devolvia zero
linhas de implementação -- os únicos acertos eram comentários, entre eles o de `ui/board_edit.py`,
que descreve `apply_edits` como *"útil para desfazer em bloco"*. A Imagem 2 põe Desfazer, Refazer e
Limpar no grupo Edição, e nenhum dos três existia.

**E o registro do que custa não tê-los já existe neste projeto: a S-76**, em que um clique
sobrescreveu 1.405 diagramas de trabalho humano. Sem histórico, uma edição errada no tabuleiro só
se desfaz reeditando casa a casa, ou recarregando o diagrama e perdendo o resto junto.

**Pilha de estados, e não de gestos.** A escolha é o item.

Uma pilha de gestos precisa saber inverter **cada** operação -- pôr, tirar, mover, arrastar,
aplicar FEN, aplicar segunda opinião, aplicar correção de rede, limpar -- e cada operação nova
precisa lembrar de registrar o seu inverso. É o tipo de contrato que se cumpre nas sete primeiras e
se esquece na oitava, e o sintoma de esquecer é um desfazer que devolve uma posição que nunca
existiu. Uma pilha de estados precisa saber **uma** coisa: a posição de antes.

O custo de memória não é argumento contra: `board_edit` é puro e `placement` é uma string de ~70
bytes; cem estados são 7 KB. O custo de correção é decisivo a favor.

**Sem `tkinter` aqui**, como em `ui/tokens.py` e `ui/comandos.py`: quem guarda o histórico não
desenha nada, e é o que permite afirmar as sete origens de mudança sem abrir janela.
"""

from __future__ import annotations

__all__ = ["TETO", "Historico"]

TETO = 100
"""Quantas posições anteriores a pilha guarda, por diagrama.

Cem porque é mais que qualquer sessão de correção observada -- a S-76 fala de diagramas com uma
dúzia de casas erradas -- e porque um teto que ninguém alcança na prática é o que faz a pilha ter
um teto sem ter um comportamento a explicar. Passar dele descarta o **mais antigo**: quem corrigiu
cem casas atrás não está querendo voltar para antes da primeira."""


class Historico:
    """As duas pilhas de um diagrama: o que foi, e o que o desfazer tirou.

    **É por diagrama, e trocar de diagrama zera as duas** (`zerar`). Desfazer para dentro de outra
    posição é pior que não desfazer: a pessoa apertaria `Ctrl+Z` esperando a casa de trás e
    receberia o tabuleiro do diagrama anterior, gravável por cima do atual com um `Ctrl+S`.

    **Salvar não passa por aqui.** Gravar em `labels.csv` é outra ação, com outro destino e outra
    reversão -- e confundir as duas é como se perderiam 1.405 linhas de novo (S-76).
    """

    __slots__ = ("_atual", "_futuro", "_passado", "_teto")

    def __init__(self, atual: str = "", *, teto: int = TETO) -> None:
        if teto < 1:
            raise ValueError(f"o teto do histórico precisa ser pelo menos 1: {teto!r}")
        self._teto = int(teto)
        self._atual = str(atual)
        self._passado: list[str] = []
        self._futuro: list[str] = []

    # ------------------------------------------------------------------------------ leitura

    @property
    def atual(self) -> str:
        """A posição que está na tela, como o histórico a conhece."""
        return self._atual

    @property
    def pode_desfazer(self) -> bool:
        return bool(self._passado)

    @property
    def pode_refazer(self) -> bool:
        return bool(self._futuro)

    @property
    def profundidade(self) -> int:
        """Quantas posições anteriores estão guardadas. Nunca passa de `TETO`."""
        return len(self._passado)

    @property
    def por_refazer(self) -> int:
        return len(self._futuro)

    # ------------------------------------------------------------------------------ escrita

    def zerar(self, atual: str = "") -> None:
        """Recomeça o histórico naquela posição. É o que a troca de diagrama chama."""
        self._atual = str(atual)
        self._passado.clear()
        self._futuro.clear()

    def registrar(self, nova: str) -> bool:
        """Uma posição nova chegou. Devolve se ela foi de fato registrada.

        **Devolve `False` para a posição que não mudou**, e isso não é economia: um clique que
        repõe a mesma peça na mesma casa passa por `on_change` como qualquer outro, e registrá-lo
        encheria a pilha de estados idênticos -- o `Ctrl+Z` seguinte não mudaria nada na tela, e a
        pessoa concluiria que o desfazer está quebrado.

        **Uma edição nova descarta o refazer**, que é a regra de toda pilha de desfazer: o futuro
        que ela guardava é de uma linha do tempo que acabou de deixar de existir.
        """
        nova = str(nova)
        if nova == self._atual:
            return False
        self._passado.append(self._atual)
        while len(self._passado) > self._teto:
            self._passado.pop(0)
        self._atual = nova
        self._futuro.clear()
        return True

    def desfazer(self) -> str | None:
        """A posição anterior, ou `None` quando não há o que desfazer."""
        if not self._passado:
            return None
        self._futuro.append(self._atual)
        self._atual = self._passado.pop()
        return self._atual

    def refazer(self) -> str | None:
        """O que o desfazer tirou, ou `None` quando não há o que refazer."""
        if not self._futuro:
            return None
        self._passado.append(self._atual)
        self._atual = self._futuro.pop()
        return self._atual
