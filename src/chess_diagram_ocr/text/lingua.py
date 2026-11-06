"""A língua do livro: detectada pelas palavras funcionais das primeiras folhas lidas, e a escolhida à mão vence (S-723).

O Tesseract precisa saber a língua, e o dono não quer dizê-la a cada livro. Aqui estão o perfil, o decisor e o estado
que o caderno guarda. Tudo puro: quem lê a folha é a janela, e quem grava é `text/caderno.py`.

**Palavra funcional, e não dicionário.** As listas da S-728 têm `after` e `avec` em sete das oito línguas, porque o corpus
delas é da web, e não separam língua nenhuma. `the`, `und`, `não` e `het` separam, e sobrevivem ao OCR ruim porque são
curtas e aparecem em toda linha.

**Só em minúscula, e nunca token de uma letra.** `De`, `Te`, `Le` e `Re` são lance em alemão, espanhol e francês; `a`, `e`
e `o` são coluna. A palavra no começo de frase se perde, e a que sobra basta.

**Sem acento dos dois lados.** O glifo troca acento, e o scan velho também: `nao` conta como `não`, e `si` como `și`.

**Uma palavra de várias línguas pesa menos**: `de` está em cinco, e vale um quinto em cada. É isso que separa português de
espanhol, que dividem `que`, `para` e `como`.

**O russo se decide pelo alfabeto**, antes de palavra nenhuma: nenhuma outra das oito é escrita em cirílico. O glifo não tem
classe de cirílico, e numa folha russa escreve latim sem sentido; **por isso a camada do PDF, quando há, é a fonte da folha**
(`texto_da_folha`). Serve mesmo sendo OCR de terceiro: para dizer a língua, ninguém precisa de letra certa em toda palavra.
Um scan russo sem camada fica sem resposta, e a pessoa escolhe.
"""

from __future__ import annotations

import hashlib
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from .fusao import NOTACAO, classe_do_token
from .tesseract import LINGUAS

__all__ = [
    "FOLHAS_DA_DETECCAO",
    "FRACAO_CIRILICA",
    "PALAVRAS_POR_FOLHA",
    "PONTOS_MINIMOS",
    "VANTAGEM_MINIMA",
    "Contagem",
    "LinguaDoLivro",
    "contar",
    "decidir",
    "sha_do_perfil",
    "texto_da_folha",
]

FOLHAS_DA_DETECCAO = 10
"""Quantas folhas lidas entram na conta. Depois disso o que está decidido fica, e reler não muda nada."""

PALAVRAS_POR_FOLHA = 20
"""Menos palavras que isto não gasta uma das dez: a capa, a folha de diagramas e o sumário não dizem a língua."""

PONTOS_MINIMOS = 6.0
"""Quanta evidência decide. Abaixo disto a resposta é "ainda não sei", e o `tessdata` fica no que estava."""

VANTAGEM_MINIMA = 1.5
"""Quantas vezes a primeira língua tem de superar a segunda. Livro que não abre esta folga fica sem resposta, e a pessoa
escolhe: **língua errada lê pior que língua nenhuma decidida**, e o menu resolve em dois cliques."""

FRACAO_CIRILICA = 0.5
"""A partir de quanto das letras em cirílico o livro é russo."""

_PERFIL: dict[str, str] = {
    "eng": "the of and to in is that it for with as on be by this at from are not but have an or his was which can if they has after white black",
    "por": "de do da dos das em no na nos nas um uma os as ao aos com para por que não se mais mas como pelo pela são está foi ou seu sua já há brancas pretas",
    "spa": "de del el la los las en un una con por para que no se es al lo más pero como su sus este esta son fue ha ya hay blancas negras",
    "deu": "der die das und ist nicht ein eine einen mit auf zu den dem des von im für sich auch als wird es so nach wenn aber wie sind an aus bei zum zur oder kann weiß schwarz",
    "nld": "de het een en van in is op te dat met voor niet aan zijn bij naar om ook als maar dan hij er door tot uit kan wordt deze dit wit zwart",
    "fra": "le la les des du de et un une en que qui est dans pour pas sur au aux par ce il se ne avec plus mais ou on sont cette blancs noirs",
    "ron": "și în de la cu pe un care nu este din mai se ce sau al ale prin pentru dar după ca sunt fi cea lui unei unui această albul negrul",
}
"""As palavras de cada língua, à mão. O russo não está aqui porque o alfabeto o decide."""


def _sem_acento(palavra: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", palavra) if not unicodedata.combining(c)).replace("ß", "ss")


def _pesos() -> dict[str, dict[str, float]]:
    """`palavra sem acento -> {língua: peso}`, com o peso repartido entre as línguas que a têm."""
    donos: dict[str, set[str]] = {}
    for lingua, palavras in _PERFIL.items():
        for palavra in palavras.split():
            donos.setdefault(_sem_acento(palavra), set()).add(lingua)
    return {palavra: {lingua: 1.0 / len(linguas) for lingua in linguas} for palavra, linguas in donos.items()}


_PESOS = _pesos()


def sha_do_perfil() -> str:
    """A identidade do perfil e das constantes. O relatório a grava, e o teste reprova relatório de outro perfil."""
    corpo = repr((sorted(_PERFIL.items()), FOLHAS_DA_DETECCAO, PALAVRAS_POR_FOLHA, PONTOS_MINIMOS, VANTAGEM_MINIMA, FRACAO_CIRILICA))
    return hashlib.sha256(corpo.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Contagem:
    """A evidência acumulada, sem texto nenhum: é o que vai ao caderno e ao relatório."""

    pontos: Mapping[str, float] = field(default_factory=dict)
    palavras: int = 0
    cirilicas: int = 0
    latinas: int = 0

    def mais(self, outra: Contagem) -> Contagem:
        pontos = dict(self.pontos)
        for lingua, valor in outra.pontos.items():
            pontos[lingua] = pontos.get(lingua, 0.0) + valor
        return Contagem(pontos, self.palavras + outra.palavras, self.cirilicas + outra.cirilicas, self.latinas + outra.latinas)

    def para_json(self) -> dict[str, Any]:
        return {
            "pontos": {lingua: round(valor, 3) for lingua, valor in sorted(self.pontos.items())},
            "palavras": self.palavras,
            "cirilicas": self.cirilicas,
            "latinas": self.latinas,
        }

    @classmethod
    def de_json(cls, dados: object) -> Contagem:
        if not isinstance(dados, Mapping):
            return cls()
        pontos = dados.get("pontos")
        try:
            return cls(
                {str(k): float(v) for k, v in pontos.items()} if isinstance(pontos, Mapping) else {},
                max(0, int(dados.get("palavras", 0))),
                max(0, int(dados.get("cirilicas", 0))),
                max(0, int(dados.get("latinas", 0))),
            )
        except (TypeError, ValueError):
            return cls()


_BORDA = ".,;:!?()[]{}'\"“”‘’«»—–-"


def contar(texto: str) -> Contagem:
    """A evidência de um texto: as palavras em minúscula que não são notação, e as letras de cada alfabeto."""
    pontos: dict[str, float] = {}
    palavras = cirilicas = latinas = 0
    for bruto in texto.split():
        token = bruto.strip(_BORDA)
        if not token or classe_do_token(token) == NOTACAO or not any(c.isalpha() for c in token):
            continue
        palavras += 1
        for c in token:
            if "Ѐ" <= c <= "ӿ":
                cirilicas += 1
            elif c.isascii() and c.isalpha():
                latinas += 1
        # O perfil está em minúscula, e nenhuma palavra dele tem uma letra só: `De` e `a` não casam com nada aqui.
        for lingua, peso in _PESOS.get(_sem_acento(token), {}).items():
            pontos[lingua] = pontos.get(lingua, 0.0) + peso
    return Contagem(pontos, palavras, cirilicas, latinas)


def decidir(contagem: Contagem) -> str:
    """A língua desta evidência, ou `""` quando ela não basta. Ver `PONTOS_MINIMOS` e `VANTAGEM_MINIMA`."""
    letras = contagem.cirilicas + contagem.latinas
    if letras and contagem.cirilicas / letras >= FRACAO_CIRILICA:
        return "rus"
    ordem = sorted(contagem.pontos.items(), key=lambda par: (-par[1], par[0]))
    if not ordem or ordem[0][1] < PONTOS_MINIMOS:
        return ""
    if len(ordem) > 1 and ordem[0][1] < VANTAGEM_MINIMA * ordem[1][1]:
        return ""
    return ordem[0][0]


def texto_da_folha(camada: str, lido: str) -> str:
    """De onde a folha conta: a camada, se ela traz palavras que bastem para a folha valer; senão, o que o motor leu."""
    return camada if contar(camada).palavras >= PALAVRAS_POR_FOLHA else lido


@dataclass(frozen=True)
class LinguaDoLivro:
    """O que o caderno guarda: a escolhida à mão, a detectada, e a conta de onde esta saiu."""

    manual: str = ""
    detectada: str = ""
    folhas: tuple[int, ...] = ()
    contagem: Contagem = field(default_factory=Contagem)

    def efetiva(self, padrao: str = "") -> str:
        """**A manual sempre vence a detectada**, e `padrao` é quem responde quando não há nenhuma das duas."""
        return self.manual or self.detectada or padrao

    def com_folha(self, pagina: int, texto: str) -> LinguaDoLivro:
        """Soma uma folha lida. Reler a mesma não conta de novo, e depois das dez nada muda."""
        if pagina in self.folhas or len(self.folhas) >= FOLHAS_DA_DETECCAO:
            return self
        contagem = contar(texto)
        if contagem.palavras < PALAVRAS_POR_FOLHA:
            return self
        somada = self.contagem.mais(contagem)
        return replace(self, folhas=(*self.folhas, int(pagina)), contagem=somada, detectada=decidir(somada))

    def com_manual(self, codigo: str) -> LinguaDoLivro:
        """A escolha à mão. `""` devolve a decisão à detecção, com a conta dela intacta."""
        return replace(self, manual=codigo if codigo in LINGUAS else "")

    def para_json(self) -> dict[str, Any]:
        return {
            "manual": self.manual,
            "detectada": self.detectada,
            "folhas": [p + 1 for p in self.folhas],
            "contagem": self.contagem.para_json(),
        }

    @classmethod
    def de_json(cls, dados: object) -> LinguaDoLivro:
        """Do arquivo do caderno. O que não for um código conhecido vira "sem língua", e nunca um erro ao abrir o livro."""
        if not isinstance(dados, Mapping):
            return cls()
        manual, detectada = str(dados.get("manual", "")), str(dados.get("detectada", ""))
        folhas = dados.get("folhas")
        try:
            paginas = tuple(int(f) - 1 for f in folhas) if isinstance(folhas, (list, tuple)) else ()
        except (TypeError, ValueError):
            paginas = ()
        return cls(
            manual if manual in LINGUAS else "",
            detectada if detectada in LINGUAS else "",
            paginas,
            Contagem.de_json(dados.get("contagem")),
        )
