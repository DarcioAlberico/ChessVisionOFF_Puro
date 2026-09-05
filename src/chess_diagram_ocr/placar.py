"""O placar do treino: por livro, para sempre, e por sessão (S-541).

**O que havia.** `qt/painel_de_estudo.py` contava `self._acertos` e `self._erros` em dois inteiros
que `alternar_treino` zerava -- o placar morria ao desligar o treino, e desligar o treino é o gesto
declarado para guardar um lance que se quis jogar. Trinta minutos de exercício deixavam de rastro
uma frase que já tinha sumido.

**Duas escalas, e as duas fazem falta por razões diferentes.**

- A **sessão** responde *como estou hoje* e é o que muda a decisão de continuar ou parar. Ela não é
  gravada: uma sessão que sobrevive ao fechamento do programa não é uma sessão.
- O **livro** responde *como estou neste material*, e é ela que dá sentido a um acervo de centenas
  de livros -- `78% em 214 lances no Reinfeld` é a frase que diz qual livro reabrir. É gravada.

**Três baldes, e não dois.** Certo, equivalente e errado: o lance que a linha dá, o lance que o
motor considera igualmente bom, e o que perde. Sem o balde do meio, um treino contra uma partida de
torneio classifica como erro toda transposição e todo lance de igual valor -- e o placar passa a
medir a memória da partida em vez do xadrez de quem treina. Quem decide em que balde cai é
`ui/treino_declarado.classificar_o_lance`, com a régua de perda da S-537.

A perda em centipeões é somada por livro para o placar poder dizer **quanto** se perde em média, e
não só quantas vezes: dois lances errados de 60 centipeões não são um erro grave.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .config import PROJECT_ROOT

logger = logging.getLogger(__name__)

__all__ = [
    "CAMINHO_PADRAO",
    "CERTO",
    "ERRADO",
    "EQUIVALENTE",
    "ESQUEMA",
    "RESULTADOS",
    "Placar",
    "PlacarDoLivro",
    "carregar",
    "gravar",
]

CAMINHO_PADRAO = PROJECT_ROOT / "data" / "placar.json"
ESQUEMA = 1

CERTO = "certo"
EQUIVALENTE = "equivalente"
ERRADO = "errado"
"""Os três baldes. Chaves e não texto de tela -- quem os escreve é `ui/treino_declarado.py`."""

RESULTADOS: tuple[str, ...] = (CERTO, EQUIVALENTE, ERRADO)


@dataclass(frozen=True)
class PlacarDoLivro:
    """Quantos lances, de cada tipo, e quanto se perdeu neles.

    **`perda` é a soma e não a média**, e é assim que ela tem de ser gravada: a média de duas
    sessões não é a média das médias, e recalculá-la a partir da soma é a única forma de o número
    continuar certo depois de somar o placar de hoje ao de ontem.
    """

    livro: str = ""
    certos: int = 0
    equivalentes: int = 0
    errados: int = 0
    perda: int = 0
    """Centipeões perdidos, somados sobre **todos** os lances -- inclusive os certos, que perdem
    zero. É o que faz a média significar "quanto custa um lance meu neste livro"."""

    @property
    def total(self) -> int:
        return self.certos + self.equivalentes + self.errados

    @property
    def bons(self) -> int:
        """Certos mais equivalentes: os lances que não custaram nada."""
        return self.certos + self.equivalentes

    @property
    def acerto(self) -> float:
        """Fração de lances bons, de 0 a 1. Placar vazio vale zero -- não há o que afirmar."""
        return (self.bons / self.total) if self.total else 0.0

    @property
    def perda_media(self) -> float:
        """Centipeões perdidos por lance. Zero num placar vazio."""
        return (self.perda / self.total) if self.total else 0.0

    def com(self, resultado: str, *, perda: int = 0) -> PlacarDoLivro:
        """Este placar mais um lance. Resultado desconhecido levanta -- ver `RESULTADOS`."""
        if resultado not in RESULTADOS:
            raise KeyError(f"resultado desconhecido: {resultado!r}. Os válidos estão em RESULTADOS.")
        campo = {CERTO: "certos", EQUIVALENTE: "equivalentes", ERRADO: "errados"}[resultado]
        return replace(
            self,
            **{campo: getattr(self, campo) + 1},
            perda=self.perda + max(0, int(perda)),
        )

    def para_json(self) -> dict[str, Any]:
        return {
            "livro": self.livro,
            "certos": self.certos,
            "equivalentes": self.equivalentes,
            "errados": self.errados,
            "perda": self.perda,
        }

    @classmethod
    def de_json(cls, dados: Any) -> PlacarDoLivro:
        bruto = dados if isinstance(dados, dict) else {}
        return cls(
            livro=str(bruto.get("livro", "")),
            certos=int(bruto.get("certos", 0)),
            equivalentes=int(bruto.get("equivalentes", 0)),
            errados=int(bruto.get("errados", 0)),
            perda=int(bruto.get("perda", 0)),
        )


@dataclass
class Placar:
    """O placar inteiro: um por livro, mais o da sessão em curso.

    **Mutável, e é a exceção deste projeto.** Os dados de domínio daqui são congelados porque
    atravessam threads e são serializados; este objeto é um contador que a sala segura enquanto a
    janela está aberta, e uma versão imutável obrigaria o painel a reatribuir um atributo a cada
    lance -- que é o desenho em que se esquece de reatribuir uma vez e o placar para de contar.
    """

    livros: dict[str, PlacarDoLivro] = field(default_factory=dict)
    sessao: PlacarDoLivro = field(default_factory=PlacarDoLivro)
    """O da sessão em curso. **Não é gravado**: ver o cabeçalho."""

    origem: Path | None = None
    """De onde este placar foi lido -- e, por isso, para onde ele volta (S-541).

    **Existe porque o placar atravessa uma janela que não sabe o caminho dele.** A sala carrega o
    arquivo de `pasta_de_treino/placar.json` e passa o objeto para `qt/painel_de_treino`, que conta
    os lances do exercício; a janela não tem como saber que pasta é essa, e um `CAMINHO_PADRAO`
    cravado lá gravaria no lugar errado -- em `data/placar.json`, que ninguém relê. O resultado era
    o defeito medido em 2026-09-04: trinta exercícios respondidos, `placar.json` nunca criado, e
    zeros ao reabrir.

    `None` é o placar que não veio do disco -- o de um teste, ou o de quem treina numa posição
    colada à mão --, e `gravar` sem destino explícito então cai em `CAMINHO_PADRAO`, que é o
    contrato de antes deste campo existir."""

    def registrar(self, livro: str, resultado: str, *, perda: int = 0) -> None:
        """Conta um lance, no livro e na sessão.

        Livro vazio conta **só** na sessão, e é o caso de quem treina numa posição colada à mão:
        gravar um placar sob a chave `""` criaria um "livro sem nome" que cresce para sempre e não
        responde a pergunta nenhuma.
        """
        self.sessao = self.sessao.com(resultado, perda=perda)
        nome = str(livro or "").strip()
        if not nome:
            return
        atual = self.livros.get(nome, PlacarDoLivro(livro=nome))
        self.livros[nome] = atual.com(resultado, perda=perda)

    def do_livro(self, livro: str) -> PlacarDoLivro:
        """O placar daquele livro, ou um vazio -- nunca `None`: quem mostra não trata ausência."""
        return self.livros.get(str(livro or "").strip(), PlacarDoLivro(livro=str(livro or "")))

    def zerar_sessao(self) -> None:
        self.sessao = PlacarDoLivro()

    @property
    def total(self) -> PlacarDoLivro:
        """A soma de todos os livros -- o placar do acervo."""
        somado = PlacarDoLivro(livro="")
        for placar in self.livros.values():
            somado = replace(
                somado,
                certos=somado.certos + placar.certos,
                equivalentes=somado.equivalentes + placar.equivalentes,
                errados=somado.errados + placar.errados,
                perda=somado.perda + placar.perda,
            )
        return somado


def carregar(*, caminho: Path | None = None) -> Placar:
    """O placar gravado. Vazio quando não há arquivo -- **e sempre com a origem** (ver `origem`).

    O caminho é guardado mesmo quando o arquivo não existe: um placar que ainda está vazio é
    exatamente o que precisa saber onde nascer.
    """
    origem = Path(caminho) if caminho is not None else CAMINHO_PADRAO
    if not origem.exists():
        return Placar(origem=origem)
    try:
        dados = json.loads(origem.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        logger.warning("O placar do treino não pôde ser lido (%s): %s", origem, erro)
        return Placar(origem=origem)
    if not isinstance(dados, dict) or int(dados.get("esquema", ESQUEMA)) > ESQUEMA:
        logger.warning("%s: esquema desconhecido ou topo que não é objeto.", origem.name)
        return Placar(origem=origem)
    achados: dict[str, PlacarDoLivro] = {}
    for bruto in dados.get("livros", []):
        placar = PlacarDoLivro.de_json(bruto)
        if placar.livro:
            achados[placar.livro] = placar
    return Placar(livros=achados, origem=origem)


def gravar(placar: Placar | Iterable[PlacarDoLivro], *, caminho: Path | None = None) -> Path:
    """Grava o placar por livro. A sessão não vai junto -- ver o cabeçalho.

    **Sem `caminho`, o destino é a origem do próprio placar**, e só depois `CAMINHO_PADRAO`: quem
    tem o objeto nem sempre tem a pasta de onde ele veio, e essa é a razão de `Placar.origem`
    existir.
    """
    da_origem = getattr(placar, "origem", None) if isinstance(placar, Placar) else None
    destino = Path(caminho) if caminho is not None else (da_origem or CAMINHO_PADRAO)
    lista = list(placar.livros.values()) if isinstance(placar, Placar) else list(placar)
    atomic_write_json(
        destino,
        {
            "esquema": ESQUEMA,
            "livros": [p.para_json() for p in sorted(lista, key=lambda p: p.livro)],
        },
    )
    return destino
