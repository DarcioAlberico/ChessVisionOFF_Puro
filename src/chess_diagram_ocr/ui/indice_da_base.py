"""O que a barra do índice da base **diz** e **quanto** anda, sem toolkit (S-532).

`games_index.build_index` avisa `(base, bytes_lidos, bytes_totais, partidas)` até dez vezes por
segundo, arquivo a arquivo. A janela precisa transformar isso em duas coisas: um número por mil
para a barra do **conjunto** -- que anda também pelo que foi pulado, senão uma pasta em que só um
arquivo mudou mostraria a barra parada em zero durante o único arquivo lido --, e uma frase que
diz em que arquivo está e quanto falta.

As duas são decisão, e por isso moram aqui e não em `qt/indice_da_base.py`: a mesma frase tem de
sair igual na barra do rodapé e no diálogo, e a régua da barra é o que o teste afirma sem janela.
"""

from __future__ import annotations

from collections.abc import Mapping

__all__ = [
    "POR_MIL",
    "Andamento",
    "frase_de_fim",
    "frase_de_progresso",
    "perde_trabalho_ao_fechar",
]

POR_MIL = 1000
"""A escala da barra: mil passos são suficientes para um arquivo de gigabytes andar sem saltar, e
cabem num `int` de `QProgressDialog` sem conversão."""


def _legivel(bytes_: int) -> str:
    """`8,6 GB`, `62 MB`, `40 kB` -- como quem vai esperar por ele o lê (`escolha_de_bases`)."""
    if bytes_ >= 1_000_000_000:
        return f"{bytes_ / 1e9:.1f} GB".replace(".", ",")
    if bytes_ >= 1_000_000:
        return f"{bytes_ / 1e6:.0f} MB"
    return f"{bytes_ / 1e3:.0f} kB"


class Andamento:
    """A soma do que já foi lido sobre o conjunto de bases, arquivo a arquivo.

    Guarda o último aviso de cada arquivo -- e não a soma corrida -- porque cada aviso traz a
    posição absoluta naquele arquivo, e um arquivo pulado chega de uma vez com os bytes cheios.
    """

    def __init__(self, tamanhos: Mapping[str, int]) -> None:
        self._tamanhos = dict(tamanhos)
        self._lidos: dict[str, int] = {}
        self.total = sum(self._tamanhos.values())

    def registrar(self, nome: str, bytes_lidos: int, bytes_totais: int) -> int:
        """Anota o aviso e devolve o andamento do conjunto, em `POR_MIL`."""
        if nome not in self._tamanhos:
            # Uma base que a lista nao previa (o indice conhece o que a janela nao listou):
            # entra no total para a barra nao passar de mil.
            self._tamanhos[nome] = bytes_totais
            self.total += bytes_totais
        self._lidos[nome] = min(bytes_lidos, self._tamanhos[nome])
        return self.por_mil

    @property
    def por_mil(self) -> int:
        if self.total <= 0:
            return POR_MIL
        return min(POR_MIL, (sum(self._lidos.values()) * POR_MIL) // self.total)


def frase_de_progresso(nome: str, bytes_lidos: int, bytes_totais: int, partidas: int) -> str:
    """`Lendo base.pgn: 1,2 GB de 8,6 GB · 1.234.567 partidas` -- ou `base.pgn: sem mudança`."""
    if bytes_totais > 0 and bytes_lidos >= bytes_totais and partidas == 0:
        return f"{nome}: sem mudança, não foi relido"
    onde = f"{_legivel(bytes_lidos)} de {_legivel(bytes_totais)}" if bytes_totais > 0 else "arquivo vazio"
    # O ponto de milhar so no numero de partidas: `1,2 GB` tem virgula decimal e ficaria `1.2 GB`.
    contagem = f"{partidas:,}".replace(",", ".")
    return f"Lendo {nome}: {onde} · {contagem} partidas"


def frase_de_fim(
    partidas: int,
    relidas: int,
    arquivos_relidos: int,
    arquivos_pulados: int,
    arquivos_removidos: int,
    cancelado: bool,
) -> str:
    """O que o rodapé diz quando a rodada acaba. Diz **o que não foi relido**, que é o item."""
    if cancelado:
        return (
            f"Índice da base interrompido: {relidas:,} partidas lidas ficaram gravadas, e a próxima "
            "rodada continua de onde parou. Até lá a busca por nome não usa o índice."
        ).replace(",", ".")
    partes = [f"{partidas:,} partidas no índice".replace(",", ".")]
    if arquivos_relidos:
        partes.append(f"{relidas:,} lidas de {arquivos_relidos} arquivo(s)".replace(",", "."))
    if arquivos_pulados:
        partes.append(f"{arquivos_pulados} arquivo(s) sem mudança, não relido(s)")
    if arquivos_removidos:
        partes.append(f"{arquivos_removidos} arquivo(s) que saíram da pasta")
    return "Índice da base em dia: " + "; ".join(partes) + "."


def perde_trabalho_ao_fechar() -> bool:
    """Fechar a janela no meio do índice **não** perde trabalho gravado (S-532).

    Cada arquivo é uma transação: o que terminou fica, o arquivo em curso é desfeito e a rodada
    seguinte continua dele. É o que decide o `loses_work` do `BusyRegistry` -- e é falso de
    propósito, porque dizer "vai perder trabalho" sobre uma operação que retoma treinaria a
    pessoa a ignorar o aviso quando ele for verdade (a busca por posição).
    """
    return False
