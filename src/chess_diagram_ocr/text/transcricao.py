"""O estado da transcrição das 123 faixas de referência (S-183).

**Sem `import tkinter`**, pela regra que organizou a Fase 6: o que dá para testar não mora na
janela. E aqui o que erra sem alarde é justamente o que não se vê -- navegar com o campo pela
metade, marcar `conferido` sobre texto vazio, e sobrescrever o arquivo que outra sessão acabou
de gravar.

O que este módulo **não** faz, e não é esquecimento: ele não lê motor nenhum e não oferece
"preencher automaticamente". A referência da S-183 tem de vir da página impressa -- se ela vier
de um motor, a tabela mede o motor contra ele mesmo, que é o defeito que o item existe para
evitar. A única coisa pré-preenchida é a semente da **camada de texto** do PDF, que já veio do
`--semear`, e o `Item.circular` avisa quando ela continua intocada.

Três regras que o modelo carrega, e as três são verificáveis:

1. **A semente é registro, não rascunho.** `editar` nunca escreve em `texto_semente` nem em
   `semeado_de`: eles são o que a máquina escreveu, e é comparando `texto` com eles que a
   tabela conta as células circulares.
2. **Conferido com texto vazio é permitido e avisado.** `cer()` devolve infinito quando a
   referência é vazia e o motor leu algo -- não é um zero silencioso, mas também não é o que
   alguém quis dizer ao marcar a faixa. O modelo deixa passar e coloca em `avisos()`.
3. **Gravar recusa sobrescrever arquivo que mudou no disco.** O digest do que foi lido fica
   guardado; se o arquivo mudou desde a carga, `salvar` levanta em vez de apagar conferência
   humana, que é a coisa mais cara do processo.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path

# `Faixa` e `carregar_referencia` moram no comando que mede desde a S-183, e é lá que a forma
# da linha é validada. Movê-los para cá mexeria no `cvoff-texto-placar` sem nenhum ganho: o que
# nasce aqui é a sessão de transcrição, não o formato do arquivo.
from ..atomic_io import atomic_write_text
from ..cli.texto_placar import Faixa, carregar_referencia

__all__ = ["Item", "ReferenciaMudouNoDisco", "SessaoDeTranscricao", "normalizar_texto"]


class ReferenciaMudouNoDisco(RuntimeError):
    """O arquivo de referência mudou desde que foi lido, e gravar por cima apagaria trabalho."""


def normalizar_texto(bruto: str) -> str:
    """O que o campo de texto devolve, na forma em que a referência guarda.

    O `Text` do Tk sempre entrega um `\\n` final, e um campo preenchido com Enter no fim viraria
    uma linha a mais na referência -- que a `cer` conta como caractere. Aqui a diferença entre
    "acabei com Enter" e "não acabei" deixa de existir, e o que sobra é o que está impresso.

    Espaço nas pontas de cada linha também sai: a `cer` colapsa espaço antes de comparar, então
    ele não muda número nenhum -- só produziria diferença entre duas transcrições iguais.
    """
    linhas = [linha.strip() for linha in bruto.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while linhas and not linhas[0]:
        linhas.pop(0)
    while linhas and not linhas[-1]:
        linhas.pop()
    return "\n".join(linhas)


@dataclass(frozen=True)
class Item:
    """Uma faixa, o número que a nomeia e o PNG que a mostra."""

    numero: int
    """1-based. É **a linha** do `.jsonl` e o prefixo do PNG exportado -- os dois vêm do mesmo
    `enumerate`, e é por isso que `007_p42.png` e a sétima linha são a mesma faixa."""

    faixa: Faixa
    imagem: Path | None
    """O PNG do `--exportar`, quando ele existe. `None` é caminho normal: a pasta é `sob
    demanda`, e transcrever sem ela é possível (abrindo o PDF na página), só é caro."""

    @property
    def pendente(self) -> bool:
        return not self.faixa.conferido

    @property
    def circular(self) -> bool:
        """Marcada como conferida, semeada da camada, e ninguém mudou uma letra."""
        return self.faixa.conferido and self.faixa.intocada

    @property
    def vazia(self) -> bool:
        return not self.faixa.texto.strip()

    @property
    def rotulo(self) -> str:
        return f"{self.numero:03d} · {self.faixa.pdf} · p. {self.faixa.pagina}"


class SessaoDeTranscricao:
    """Onde estou, o que editei e o que isso grava."""

    def __init__(self, referencia: Path, itens: list[Item], *, digest: str) -> None:
        self.referencia = Path(referencia)
        self.itens = itens
        self._digest = digest
        self._indice = 0
        self.sujo = False

    # ------------------------------------------------------------------ carga e gravação

    @classmethod
    def carregar(cls, referencia: Path, pngs: Path | None = None) -> SessaoDeTranscricao:
        """Lê a referência e casa cada linha com o PNG de mesmo número, quando ele existe."""
        referencia = Path(referencia)
        faixas = carregar_referencia(referencia)
        por_numero = _pngs_por_numero(pngs) if pngs is not None else {}
        itens = [
            Item(numero=numero, faixa=faixa, imagem=por_numero.get(numero))
            for numero, faixa in enumerate(faixas, start=1)
        ]
        return cls(referencia, itens, digest=_digest(referencia))

    def salvar(self) -> None:
        """Regrava o `.jsonl` inteiro, na mesma serialização do `--semear`.

        **Recusa quando o arquivo mudou no disco.** Este checkout tem mais de uma sessão
        escrevendo na mesma árvore, e a referência é o único arquivo aqui em que uma
        sobrescrita apaga horas de trabalho humano em vez de um artefato reconstruível.
        """
        atual = _digest(self.referencia)
        if atual != self._digest:
            raise ReferenciaMudouNoDisco(
                f"{self.referencia} mudou no disco desde que foi aberto. Feche esta janela sem "
                "gravar, confira o arquivo, e reabra -- gravar por cima apagaria o que a outra "
                "sessão conferiu."
            )
        corpo = "\n".join(json.dumps(item.faixa.para_json(), ensure_ascii=False) for item in self.itens)
        atomic_write_text(self.referencia, corpo + "\n")
        self._digest = _digest(self.referencia)
        self.sujo = False

    # ------------------------------------------------------------------ onde estou

    @property
    def indice(self) -> int:
        return self._indice

    @property
    def atual(self) -> Item:
        return self.itens[self._indice]

    @property
    def total(self) -> int:
        return len(self.itens)

    @property
    def conferidas(self) -> int:
        return sum(1 for item in self.itens if item.faixa.conferido)

    @property
    def circulares(self) -> int:
        return sum(1 for item in self.itens if item.circular)

    def ir_para(self, indice: int) -> bool:
        """Move para `indice` **0-based**. `False` quando ele está fora da lista."""
        if not 0 <= indice < len(self.itens) or indice == self._indice:
            return False
        self._indice = indice
        return True

    def proximo(self) -> bool:
        return self.ir_para(self._indice + 1)

    def anterior(self) -> bool:
        return self.ir_para(self._indice - 1)

    def proxima_pendente(self) -> bool:
        """A próxima ainda não conferida, dando a volta. `False` quando não sobrou nenhuma.

        **Dá a volta de propósito**: quem começa pela faixa 60 e chega ao fim ainda tem 59
        pendentes atrás, e um botão que só olha para a frente pararia dizendo "acabou" com
        metade do trabalho aberta.
        """
        ordem = list(range(self._indice + 1, len(self.itens))) + list(range(0, self._indice + 1))
        for indice in ordem:
            if self.itens[indice].pendente:
                return self.ir_para(indice)
        return False

    # ------------------------------------------------------------------ o que edito

    def editar(self, *, texto: str | None = None, conferido: bool | None = None) -> bool:
        """Escreve na faixa atual. Devolve se alguma coisa mudou de fato.

        `texto_semente` e `semeado_de` ficam de fora **sempre**: são o registro do que a
        semeadura escreveu, e é a comparação com eles que a tabela publica como
        `circulares_camada`.
        """
        item = self.atual
        novo = item.faixa
        if texto is not None:
            novo = replace(novo, texto=normalizar_texto(texto))
        if conferido is not None:
            novo = replace(novo, conferido=conferido)
        if novo == item.faixa:
            return False
        self.itens[self._indice] = replace(item, faixa=novo)
        self.sujo = True
        return True

    def restaurar_semente(self) -> bool:
        """Devolve o `texto` ao que a camada semeou. Sem semente, não faz nada."""
        item = self.atual
        if not item.faixa.semeado_de:
            return False
        return self.editar(texto=item.faixa.texto_semente)

    # ------------------------------------------------------------------ o que dizer

    def avisos(self) -> list[str]:
        """O que a sessão inteira tem de errado, em pt-BR. Lista vazia quando não tem nada.

        Nenhum deles impede gravar: os dois são decisões legítimas em algum caso, e o que não
        se pode é tomá-las sem saber. A tabela publica o segundo como `circulares_camada`.
        """
        recado = []
        vazias = [item.numero for item in self.itens if item.faixa.conferido and item.vazia]
        if vazias:
            recado.append(
                f"{len(vazias)} faixa(s) conferidas com texto vazio "
                f"({_lista(vazias)}): a referência vazia dá CER infinito para todo motor que "
                "leia alguma coisa ali."
            )
        circulares = [item.numero for item in self.itens if item.circular]
        if circulares:
            recado.append(
                f"{len(circulares)} faixa(s) conferidas continuam iguais ao que a camada de "
                f"texto semeou ({_lista(circulares)}): para elas a coluna `camada` é circular, "
                "e a tabela reporta isso."
            )
        return recado


def _lista(numeros: list[int], *, teto: int = 8) -> str:
    mostrados = ", ".join(f"{n:03d}" for n in numeros[:teto])
    return mostrados if len(numeros) <= teto else f"{mostrados}, +{len(numeros) - teto}"


def _pngs_por_numero(pngs: Path) -> dict[int, Path]:
    """`007_p42.png` -> 7. O que não começa por três dígitos não é do `--exportar` e fica fora."""
    achados: dict[int, Path] = {}
    if not Path(pngs).is_dir():
        return achados
    for caminho in sorted(Path(pngs).glob("*.png")):
        prefixo = caminho.name.split("_", 1)[0]
        if prefixo.isdigit():
            achados.setdefault(int(prefixo), caminho)
    return achados


def _digest(caminho: Path) -> str:
    """SHA-256 do arquivo, ou `""` quando ele não existe -- que é o estado antes do primeiro
    `--semear`, e não um erro."""
    caminho = Path(caminho)
    if not caminho.exists():
        return ""
    return hashlib.sha256(caminho.read_bytes()).hexdigest()
