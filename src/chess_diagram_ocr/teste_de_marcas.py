"""O teste congelado das marcas de casa: diagramas reais anotados, e a régua que pontua um leitor.

**De onde vem.** De `data/marcas/anotacoes.json`, a anotação feita na conferência da importação. Entra a
imagem que tem amostra em `samples/` e rótulo em `labels.csv`: é a amostra, e não a imagem de origem,
que o leitor recebe, e é ela que o modelo de peças leu. O teste guarda o SHA-256 da amostra, e um PNG
trocado depois do congelamento é acusado na leitura em vez de pontuado em silêncio.

**Congelado quer dizer que nada muda de lugar.** Um caso entra uma vez, e o arquivo só cresce por
`acrescentar`: anotação nova vira caso novo, e o caso que já estava continua com o gabarito do dia em
que entrou, mesmo que alguém reanote a imagem. Comparar o modelo de hoje com o de amanhã só vale se os
dois foram medidos na mesma régua.

**Nenhum treino o vê.** O modelo de marcas treina com marca sintética (`modelo_de_marcas.py`) e tira
destas amostras até a casa sem marca. Saída de um leitor não vira gabarito de outro: as anotações são
de uma pessoa, e a sugestão do detector clássico só entrou nelas depois de aceita.

**Um viés conhecido.** Boa parte das anotações nasceu de aceitar a sugestão do detector clássico, e
por isso ele tem vantagem aqui: em 2026-11-22, 179 das 181 marcas. O teste é bom para dizer se o modelo
**alcança** o detector; para dizer que ele o supera, falta o que o detector não sugeriu.

**Como pontua.** Casa a casa, nas 64 de cada diagrama. A casa sem anotação conta como "sem marca",
porque quem anotou o diagrama anotou as marcas dele todas; a marca `outra` fica fora da conta, porque
nenhum leitor tem essa classe. Uma marca lida com o tipo errado é uma falta do tipo certo e um falso
do tipo lido.

O módulo não importa Qt nem torch.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import marcas_de_casa as mc
from .arquivo_do_dono import ler_texto
from .atomic_io import atomic_write_json
from .fen_utils import square_name
from .relogio import agora_iso

__all__ = [
    "ARQUIVO_DO_TESTE",
    "SEM_MARCA",
    "TIPOS_PONTUADOS",
    "VERSAO_DO_TESTE",
    "CasoDeTeste",
    "Placar",
    "acrescentar",
    "casos_das_anotacoes",
    "conferir_amostras",
    "ler_teste",
    "pontuar",
]

VERSAO_DO_TESTE = 1

ARQUIVO_DO_TESTE = mc.ARQUIVO_DAS_MARCAS.parent / "teste_congelado.json"
"""Onde o teste congelado mora: ao lado das anotações de que ele nasce."""

SEM_MARCA = "-"
"""O rótulo da casa sem marca nas contas do placar."""

TIPOS_PONTUADOS: tuple[str, ...] = tuple(tipo for tipo in mc.TIPOS_DE_CASA if tipo != mc.OUTRA)
"""As marcas que um leitor pode dizer. `outra` é uma anotação, não uma classe."""


@dataclass(frozen=True)
class CasoDeTeste:
    """Um diagrama do teste: a amostra, o gabarito das casas e de onde ele veio."""

    amostra: str
    """O PNG em `samples/`, que é o que o leitor recebe."""
    sha256: str
    """O SHA-256 da amostra no dia em que o caso entrou."""
    casas: dict[str, str]
    """O gabarito: `{"f6": "estrela-preta"}`. Só as casas com marca."""
    livro: str = ""
    fen: str = ""
    tracos: int = 0
    """Quantos traços (seta, reta, moldura) o diagrama tem. Eles não são pontuados aqui: contam
    só para dizer quais casas atravessadas por traço o leitor teve de recusar."""
    chave: str = ""
    """A chave da anotação de origem: o SHA-256 da imagem importada."""

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "casas": dict(sorted(self.casas.items()))}

    @classmethod
    def from_dict(cls, dados: Mapping[str, object]) -> CasoDeTeste:
        casas = dados.get("casas", {})
        tracos = dados.get("tracos", 0)
        if not isinstance(casas, dict) or not isinstance(tracos, int):
            raise ValueError(f"Caso de teste malformado: {dict(dados)!r}")
        for casa, tipo in casas.items():
            mc.indice_da_casa(casa)
            if tipo not in mc.TIPOS_DE_CASA:
                raise ValueError(f"Marca desconhecida no teste: {tipo!r}")
        if not dados.get("amostra") or not dados.get("sha256"):
            raise ValueError(f"Caso de teste sem amostra ou sem SHA-256: {dict(dados)!r}")
        return cls(
            amostra=str(dados["amostra"]),
            sha256=str(dados["sha256"]),
            casas={str(casa): str(tipo) for casa, tipo in casas.items()},
            livro=str(dados.get("livro", "")),
            fen=str(dados.get("fen", "")),
            tracos=tracos,
            chave=str(dados.get("chave", "")),
        )


def _sha256(caminho: Path) -> str:
    return mc.chave_da_imagem(caminho)


def casos_das_anotacoes(anotacoes: Path, labels_csv: Path, samples_dir: Path) -> tuple[list[CasoDeTeste], list[str]]:
    """Os casos que as anotações dão hoje, e por que cada uma das outras ficou de fora.

    Fica de fora a anotação sem amostra, a amostra que não está no `labels.csv` e a que não está no
    disco: sem a amostra não há o que ler, e sem o rótulo não se sabe se a casa marcada é vazia.
    """
    if not Path(anotacoes).exists():
        # Ninguém anotou ainda: não há caso, e isso não é erro -- é o teste vazio, que quem treina diz.
        return [], []
    arquivo = mc.ArquivoDeMarcas(anotacoes)
    with Path(labels_csv).open(encoding="utf-8", newline="") as handle:
        fens = {linha["filename"]: linha.get("fen", "") for linha in csv.DictReader(handle)}

    casos: list[CasoDeTeste] = []
    fora: list[str] = []
    dados = json.loads(Path(anotacoes).read_text(encoding="utf-8"))["imagens"]
    for chave in sorted(dados):
        entrada = arquivo.entrada(chave) or {}
        marcas = arquivo.marcas_de(chave)
        amostra = str(entrada.get("amostra", ""))
        nome = entrada.get("imagem") or chave[:12]
        if not amostra:
            fora.append(f"{nome}: sem amostra em samples/")
            continue
        if amostra not in fens:
            fora.append(f"{amostra}: fora do labels.csv")
            continue
        caminho = Path(samples_dir) / amostra
        if not caminho.exists():
            fora.append(f"{amostra}: o PNG não está em {samples_dir}")
            continue
        casos.append(
            CasoDeTeste(
                amostra=amostra,
                sha256=_sha256(caminho),
                casas=dict(marcas.casas),
                livro=str(entrada.get("livro", "")),
                fen=fens[amostra],
                tracos=len(marcas.tracos),
                chave=chave,
            )
        )
    return casos, fora


def _ler_arquivo(caminho: Path) -> dict[str, object]:
    """O JSON do teste. Ilegível ou de outra versão levanta: um teste estragado não vira teste vazio."""
    try:
        dados = json.loads(ler_texto(caminho, do_usuario=False))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Teste de marcas ilegível ({caminho}): {exc}") from exc
    if not isinstance(dados, dict) or dados.get("versao") != VERSAO_DO_TESTE:
        raise ValueError(f"Teste de marcas em formato desconhecido: {caminho}")
    return dados


def ler_teste(caminho: Path) -> list[CasoDeTeste]:
    """Os casos do teste congelado. Arquivo que não existe é teste vazio; ilegível levanta."""
    caminho = Path(caminho)
    if not caminho.exists():
        return []
    casos = _ler_arquivo(caminho).get("casos", [])
    if not isinstance(casos, list):
        raise ValueError(f"Teste de marcas sem a lista de casos: {caminho}")
    return [CasoDeTeste.from_dict(caso) for caso in casos]


def acrescentar(caminho: Path, novos: list[CasoDeTeste]) -> list[CasoDeTeste]:
    """Grava no teste os casos cuja amostra ainda não está nele, e devolve os que entraram.

    O caso que já está não muda, nem quando o gabarito de agora difere: é o que faz do arquivo uma
    régua. Para mudar um caso, é preciso apagá-lo do arquivo à mão, e isso aparece no `git diff`
    de quem guarda o arquivo.
    """
    caminho = Path(caminho)
    atuais = ler_teste(caminho)
    vistos = {caso.amostra for caso in atuais}
    entram = [caso for caso in novos if caso.amostra not in vistos]
    if not entram:
        return []
    historico: list[object] = []
    if caminho.exists():
        anterior = _ler_arquivo(caminho).get("historico", [])
        historico = list(anterior) if isinstance(anterior, list) else []
    historico.append({"em": agora_iso(), "entraram": len(entram)})
    atomic_write_json(
        caminho,
        {
            "versao": VERSAO_DO_TESTE,
            "historico": historico,
            "casos": [caso.to_dict() for caso in [*atuais, *entram]],
        },
        indent=1,
    )
    return entram


def conferir_amostras(casos: list[CasoDeTeste], samples_dir: Path) -> list[str]:
    """As amostras que sumiram ou mudaram desde o congelamento. Vazia quer dizer régua de pé."""
    problemas = []
    for caso in casos:
        caminho = Path(samples_dir) / caso.amostra
        if not caminho.exists():
            problemas.append(f"{caso.amostra}: sumiu")
        elif _sha256(caminho) != caso.sha256:
            problemas.append(f"{caso.amostra}: o PNG mudou depois do congelamento")
    return problemas


@dataclass
class Placar:
    """O que um leitor fez no teste, casa a casa e diagrama a diagrama."""

    acertos: Counter[str] = field(default_factory=Counter)
    """Por tipo: a marca lida com o tipo certo."""
    faltas: Counter[str] = field(default_factory=Counter)
    """Por tipo: a marca do gabarito que o leitor não deu, ou deu com outro tipo."""
    falsos: Counter[str] = field(default_factory=Counter)
    """Por tipo lido: a marca dada onde o gabarito tem outra coisa."""
    trocas: Counter[tuple[str, str]] = field(default_factory=Counter)
    """`(gabarito, lido)` das casas em que os dois discordam. `-` é sem marca."""
    diagramas: int = 0
    diagramas_exatos: int = 0
    """Os diagramas em que as 64 casas saíram iguais ao gabarito."""
    diagramas_com_falso: int = 0
    """Os diagramas com pelo menos uma marca dada onde não havia marca nenhuma."""
    casas_ignoradas: int = 0
    """As casas de gabarito `outra`, que ficam fora da conta."""

    @property
    def marcas(self) -> int:
        return sum(self.acertos.values()) + sum(self.faltas.values())

    @property
    def revocacao(self) -> float:
        return sum(self.acertos.values()) / self.marcas if self.marcas else 1.0

    @property
    def precisao(self) -> float:
        dadas = sum(self.acertos.values()) + sum(self.falsos.values())
        return sum(self.acertos.values()) / dadas if dadas else 1.0

    def to_dict(self) -> dict[str, object]:
        return {
            "marcas": self.marcas,
            "acertos": sum(self.acertos.values()),
            "revocacao": round(self.revocacao, 4),
            "precisao": round(self.precisao, 4),
            "diagramas": self.diagramas,
            "diagramas_exatos": self.diagramas_exatos,
            "diagramas_com_falso": self.diagramas_com_falso,
            "casas_ignoradas": self.casas_ignoradas,
            "por_tipo": {
                tipo: {"acertos": self.acertos[tipo], "faltas": self.faltas[tipo], "falsos": self.falsos[tipo]}
                for tipo in TIPOS_PONTUADOS
                if self.acertos[tipo] or self.faltas[tipo] or self.falsos[tipo]
            },
            "trocas": {f"{gabarito} -> {lido}": n for (gabarito, lido), n in sorted(self.trocas.items())},
        }

    def linhas(self) -> list[str]:
        """O placar para o terminal."""
        saida = [
            f"marcas {sum(self.acertos.values())}/{self.marcas} (revocação {self.revocacao:.1%}), "
            f"precisão {self.precisao:.1%}, diagramas exatos {self.diagramas_exatos}/{self.diagramas}, "
            f"diagramas com marca inventada {self.diagramas_com_falso}"
        ]
        for tipo in TIPOS_PONTUADOS:
            if self.acertos[tipo] or self.faltas[tipo] or self.falsos[tipo]:
                total = self.acertos[tipo] + self.faltas[tipo]
                saida.append(f"  {tipo:15} {self.acertos[tipo]:4}/{total:<4} falsos {self.falsos[tipo]}")
        for (gabarito, lido), n in sorted(self.trocas.items()):
            saida.append(f"  troca {gabarito} -> {lido}: {n}")
        return saida


def pontuar(casos: list[CasoDeTeste], lidos: Mapping[str, Mapping[str, str]]) -> Placar:
    """O placar do leitor que deu `lidos[amostra] = {"f6": "estrela-preta", ...}`.

    Amostra ausente de `lidos` conta como leitor que não deu marca nenhuma nela: um leitor que
    falha calado num diagrama não pode sair com placar melhor por isso.
    """
    placar = Placar()
    for caso in casos:
        lido = lidos.get(caso.amostra, {})
        exato = True
        inventou = False
        for indice in range(64):
            casa = square_name(indice)
            gabarito = caso.casas.get(casa, SEM_MARCA)
            if gabarito == mc.OUTRA:
                placar.casas_ignoradas += 1
                continue
            resposta = lido.get(casa, SEM_MARCA)
            if resposta == gabarito:
                if gabarito != SEM_MARCA:
                    placar.acertos[gabarito] += 1
                continue
            exato = False
            placar.trocas[(gabarito, resposta)] += 1
            if gabarito != SEM_MARCA:
                placar.faltas[gabarito] += 1
            if resposta != SEM_MARCA:
                placar.falsos[resposta] += 1
                inventou = inventou or gabarito == SEM_MARCA
        placar.diagramas += 1
        placar.diagramas_exatos += int(exato)
        placar.diagramas_com_falso += int(inventou)
    return placar
