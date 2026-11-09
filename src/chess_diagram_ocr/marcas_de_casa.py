"""As marcas impressas num diagrama: o que elas são, onde estão e onde ficam gravadas.

Livro de finais marca casa com bolinha, estrela, X e cruz, e desenha seta, reta e moldura por cima
do tabuleiro. **A marca não é peça**: a FEN continua dizendo só a posição, e a casa com estrela é
vazia para o modelo de peças. Este módulo é a outra metade da resposta -- a que diz que ali havia
uma estrela --, e é o rótulo do dataset de marcas e a fonte das conversões futuras.

**Duas famílias, porque são duas perguntas.** A marca de casa pertence a uma casa, e um classificador
por casa a lê. O traço atravessa casas e tem geometria: guarda dois pontos em unidades de casa, com
`(0, 0)` no canto superior esquerdo de a8 e `(8, 8)` no canto inferior direito de h1, para o começo
de uma reta poder estar no canto de uma casa, como os livros imprimem. Seta com curva são dois
traços: uma reta e uma seta.

**Mora fora de `labels.csv`, de propósito.** `labels.py` está no caminho de medição (S-218), e mudar
o formato dele vence os relatórios de campo. O arquivo daqui é só das marcas e aponta para a amostra
de `samples/` depois que ela existe.

**A chave é o conteúdo da imagem, e não o caminho.** O acervo tem livros duplicados, e a mesma imagem
aberta por outra pasta tem de mostrar a marca que já foi anotada. O caminho vai junto só como nota.

**Sem entrada não quer dizer "sem marca"**: quer dizer que ninguém anotou. O censo de negativos é
outra coisa, e não sai deste arquivo.

**Arquivo ilegível nunca é sobrescrito.** A anotação é trabalho manual, e tratar um arquivo estragado
como vazio apagaria tudo na gravação seguinte. Quem lê recebe `ValueError` e decide o que dizer.

O módulo não importa Qt nem torch.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_json
from .config import DATA_DIR
from .relogio import agora_iso

logger = logging.getLogger(__name__)

__all__ = [
    "ARQUIVO_DAS_MARCAS",
    "BOLINHA_BRANCA",
    "BOLINHA_PRETA",
    "CRUZ",
    "ESTRELA_BRANCA",
    "ESTRELA_PRETA",
    "MOLDURA",
    "NOMES",
    "OUTRA",
    "RETA",
    "SETA",
    "TIPOS_DE_CASA",
    "TIPOS_DE_TRACO",
    "X",
    "ArquivoDeMarcas",
    "MarcasDoDiagrama",
    "Traco",
    "chave_da_imagem",
    "descrever",
    "indice_da_casa",
    "na_grade",
]

BOLINHA_BRANCA = "bolinha-branca"
BOLINHA_PRETA = "bolinha-preta"
ESTRELA_BRANCA = "estrela-branca"
ESTRELA_PRETA = "estrela-preta"
X = "x"
CRUZ = "cruz"
OUTRA = "outra"
"""Um símbolo de casa que o vocabulário ainda não conhece. Melhor que forçá-lo a parecer outro."""

TIPOS_DE_CASA: tuple[str, ...] = (BOLINHA_BRANCA, BOLINHA_PRETA, ESTRELA_BRANCA, ESTRELA_PRETA, X, CRUZ, OUTRA)

SETA = "seta"
RETA = "reta"
MOLDURA = "moldura"
TIPOS_DE_TRACO: tuple[str, ...] = (SETA, RETA, MOLDURA)

NOMES: dict[str, str] = {
    BOLINHA_BRANCA: "bolinha branca",
    BOLINHA_PRETA: "bolinha preta",
    ESTRELA_BRANCA: "estrela branca",
    ESTRELA_PRETA: "estrela preta",
    X: "X",
    CRUZ: "cruz",
    OUTRA: "outra marca",
    SETA: "seta",
    RETA: "reta",
    MOLDURA: "moldura",
}

ARQUIVO_DAS_MARCAS = DATA_DIR / "marcas" / "anotacoes.json"

VERSAO_DO_ARQUIVO = 1

PASSO_DA_GRADE = 0.5
"""O traço pousa em centros, meios de lado e cantos de casa: é onde os livros o começam e terminam,
e sem isso a mesma seta anotada duas vezes teria duas geometrias."""

TOLERANCIA_DO_TRACO = 0.35
"""A que distância de um traço, em casas, o botão direito ainda o alcança."""

_CASA = re.compile(r"^[a-h][1-8]$")

Ponto = tuple[float, float]


def indice_da_casa(nome: str) -> int:
    """`"a8"` -> 0, `"h1"` -> 63: a ordem de leitura de `labels_from_fen` e do modelo."""
    if not _CASA.match(nome):
        raise ValueError(f"Casa inválida: {nome!r}")
    return (8 - int(nome[1])) * 8 + "abcdefgh".index(nome[0])


def na_grade(x: float, y: float) -> Ponto:
    """O ponto mais próximo da grade de meia casa, dentro do tabuleiro."""

    def pousar(valor: float) -> float:
        return min(8.0, max(0.0, round(valor / PASSO_DA_GRADE) * PASSO_DA_GRADE))

    return pousar(x), pousar(y)


def _ponto(valor: Any) -> Ponto:
    if not isinstance(valor, list | tuple) or len(valor) != 2:
        raise ValueError(f"Ponto inválido: {valor!r}")
    x, y = float(valor[0]), float(valor[1])
    if not (0.0 <= x <= 8.0 and 0.0 <= y <= 8.0):
        raise ValueError(f"Ponto fora do tabuleiro: {valor!r}")
    return x, y


def _distancia_ao_segmento(ponto: Ponto, a: Ponto, b: Ponto) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    quadrado = dx * dx + dy * dy
    t = 0.0 if quadrado == 0 else max(0.0, min(1.0, ((ponto[0] - a[0]) * dx + (ponto[1] - a[1]) * dy) / quadrado))
    return math.hypot(ponto[0] - (a[0] + t * dx), ponto[1] - (a[1] + t * dy))


@dataclass(frozen=True)
class Traco:
    """Uma seta, uma reta ou uma moldura. A seta aponta de `de` para `para`."""

    tipo: str
    de: Ponto
    para: Ponto

    def distancia(self, ponto: Ponto) -> float:
        """Distância do ponto até a linha. Na moldura conta a borda: o miolo dela é tabuleiro."""
        if self.tipo != MOLDURA:
            return _distancia_ao_segmento(ponto, self.de, self.para)
        (x0, y0), (x1, y1) = self.de, self.para
        cantos = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        return min(_distancia_ao_segmento(ponto, cantos[i], cantos[(i + 1) % 4]) for i in range(4))

    def to_dict(self) -> dict[str, Any]:
        return {"tipo": self.tipo, "de": list(self.de), "para": list(self.para)}

    @classmethod
    def from_dict(cls, dados: Any) -> Traco:
        if not isinstance(dados, dict) or dados.get("tipo") not in TIPOS_DE_TRACO:
            raise ValueError(f"Traço inválido: {dados!r}")
        return cls(dados["tipo"], _ponto(dados.get("de")), _ponto(dados.get("para")))


@dataclass(frozen=True)
class MarcasDoDiagrama:
    """As marcas de um diagrama. Cada operação devolve um valor novo."""

    casas: dict[str, str] = field(default_factory=dict)
    """`{"f6": "estrela-preta"}`. Uma marca por casa: é o rótulo de um classificador por casa."""

    tracos: tuple[Traco, ...] = ()

    @property
    def vazia(self) -> bool:
        return not self.casas and not self.tracos

    def alternar_casa(self, tipo: str, casa: str) -> MarcasDoDiagrama:
        """Põe a marca. A mesma marca na mesma casa sai; outra marca na casa é trocada por esta."""
        if tipo not in TIPOS_DE_CASA:
            raise ValueError(f"Marca de casa desconhecida: {tipo!r}")
        indice_da_casa(casa)
        novas = dict(self.casas)
        if novas.get(casa) == tipo:
            del novas[casa]
        else:
            novas[casa] = tipo
        return replace(self, casas=novas)

    def sem_casa(self, casa: str) -> MarcasDoDiagrama:
        if casa not in self.casas:
            return self
        return replace(self, casas={nome: tipo for nome, tipo in self.casas.items() if nome != casa})

    def com_traco(self, tipo: str, de: Ponto, para: Ponto) -> MarcasDoDiagrama:
        """Acrescenta o traço. Sem comprimento ou repetido não entra: nada mudou."""
        if tipo not in TIPOS_DE_TRACO:
            raise ValueError(f"Traço desconhecido: {tipo!r}")
        if tipo == MOLDURA:
            # A moldura não tem sentido: dois arrastos pelos mesmos cantos são a mesma moldura.
            de, para = (min(de[0], para[0]), min(de[1], para[1])), (max(de[0], para[0]), max(de[1], para[1]))
            if de[0] == para[0] or de[1] == para[1]:
                return self
        if de == para:
            return self
        traco = Traco(tipo, de, para)
        if traco in self.tracos:
            return self
        return replace(self, tracos=(*self.tracos, traco))

    def sem_traco_perto(self, ponto: Ponto, tolerancia: float = TOLERANCIA_DO_TRACO) -> MarcasDoDiagrama:
        """Tira o traço mais próximo do ponto, se algum estiver dentro da tolerância."""
        if not self.tracos:
            return self
        distancia, posicao = min((traco.distancia(ponto), i) for i, traco in enumerate(self.tracos))
        if distancia > tolerancia:
            return self
        return replace(self, tracos=self.tracos[:posicao] + self.tracos[posicao + 1 :])

    def to_dict(self) -> dict[str, Any]:
        return {"casas": dict(sorted(self.casas.items())), "tracos": [traco.to_dict() for traco in self.tracos]}

    @classmethod
    def from_dict(cls, dados: Any) -> MarcasDoDiagrama:
        """Lê com rigor: um valor estranho é arquivo estragado, e não marca a ignorar."""
        if not isinstance(dados, dict):
            raise ValueError(f"Marcas inválidas: {dados!r}")
        casas = dados.get("casas", {})
        if not isinstance(casas, dict):
            raise ValueError(f"Marcas de casa inválidas: {casas!r}")
        for casa, tipo in casas.items():
            indice_da_casa(casa)
            if tipo not in TIPOS_DE_CASA:
                raise ValueError(f"Marca de casa desconhecida: {tipo!r}")
        return cls(casas=dict(casas), tracos=tuple(Traco.from_dict(traco) for traco in dados.get("tracos", ())))


def descrever(marcas: MarcasDoDiagrama) -> str:
    """A frase da tela: `"estrela preta em a6, b6; 1 seta"`. Vazia quando não há marca."""
    partes = []
    for tipo in TIPOS_DE_CASA:
        casas = sorted(casa for casa, marca in marcas.casas.items() if marca == tipo)
        if casas:
            partes.append(f"{NOMES[tipo]} em {', '.join(casas)}")
    for tipo in TIPOS_DE_TRACO:
        quantos = sum(1 for traco in marcas.tracos if traco.tipo == tipo)
        if quantos:
            partes.append(f"{quantos} {NOMES[tipo]}" + ("s" if quantos > 1 else ""))
    return "; ".join(partes)


def chave_da_imagem(caminho: Path | str) -> str:
    """O SHA-256 do arquivo: a mesma imagem tem a mesma chave em qualquer pasta."""
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


class ArquivoDeMarcas:
    """O `anotacoes.json`: as marcas de cada imagem anotada.

    Cada gravação relê o disco antes de escrever, para duas janelas abertas não apagarem uma o
    trabalho da outra, e escreve atomicamente. Abrir um arquivo ilegível levanta `ValueError`, e ele
    fica como está.
    """

    def __init__(self, caminho: Path | str | None = None) -> None:
        self.caminho = Path(caminho) if caminho is not None else ARQUIVO_DAS_MARCAS
        self._entradas = self._ler()

    def __len__(self) -> int:
        return len(self._entradas)

    def _ler(self) -> dict[str, dict[str, Any]]:
        if not self.caminho.exists():
            return {}
        try:
            dados = json.loads(self.caminho.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Arquivo de marcas ilegível ({self.caminho}): {exc}") from exc
        if not isinstance(dados, dict) or dados.get("versao") != VERSAO_DO_ARQUIVO:
            raise ValueError(f"Arquivo de marcas em formato desconhecido: {self.caminho}")
        imagens = dados.get("imagens")
        if not isinstance(imagens, dict):
            raise ValueError(f"Arquivo de marcas sem a lista de imagens: {self.caminho}")
        for entrada in imagens.values():
            MarcasDoDiagrama.from_dict(entrada)
        return imagens

    def _escrever(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.caminho, {"versao": VERSAO_DO_ARQUIVO, "imagens": self._entradas}, indent=1)

    def marcas_de(self, chave: str) -> MarcasDoDiagrama:
        entrada = self._entradas.get(chave)
        return MarcasDoDiagrama() if entrada is None else MarcasDoDiagrama.from_dict(entrada)

    def entrada(self, chave: str) -> dict[str, Any] | None:
        """O que está gravado para esta imagem, com as notas. `None` é "ninguém anotou"."""
        entrada = self._entradas.get(chave)
        return None if entrada is None else dict(entrada)

    def gravar(
        self,
        chave: str,
        marcas: MarcasDoDiagrama,
        *,
        imagem: str = "",
        livro: str = "",
        amostra: str = "",
        recorte: str = "",
    ) -> None:
        """Grava as marcas da imagem. Sem marca nenhuma a entrada sai: voltou a "ninguém anotou"."""
        self._entradas = self._ler()
        if marcas.vazia:
            if self._entradas.pop(chave, None) is not None:
                self._escrever()
            return
        anterior = self._entradas.get(chave, {})
        self._entradas[chave] = {
            **marcas.to_dict(),
            "imagem": imagem or anterior.get("imagem", ""),
            "livro": livro or anterior.get("livro", ""),
            "amostra": amostra or anterior.get("amostra", ""),
            "recorte": recorte or anterior.get("recorte", ""),
            "anotado_em": agora_iso(),
        }
        self._escrever()

    def vincular_amostra(self, chave: str, amostra: str, recorte: str = "") -> bool:
        """Liga a anotação ao PNG de `samples/`. `False` quando não há anotação ou nada mudou."""
        self._entradas = self._ler()
        entrada = self._entradas.get(chave)
        if entrada is None or not amostra:
            return False
        if entrada.get("amostra") == amostra and (not recorte or entrada.get("recorte") == recorte):
            return False
        entrada["amostra"] = amostra
        if recorte:
            entrada["recorte"] = recorte
        self._escrever()
        return True
