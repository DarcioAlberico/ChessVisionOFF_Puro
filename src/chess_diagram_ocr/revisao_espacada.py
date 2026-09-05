"""A repetição espaçada dos estudos e das táticas: FSRS, e por que não SM-2 (S-540).

**O que se agenda aqui.** Um exercício da S-539 e um estudo da sala são a mesma coisa para este
módulo: uma **chave** que se acerta ou se erra, com uma data em que vale a pena voltar a ela. Nada
aqui sabe o que é um lance.

## A escolha do algoritmo, e ela é a decisão do item

Dois candidatos sérios em 2026: o **SM-2** do SuperMemo, que o Anki usou por trinta anos, e o
**FSRS** (*Free Spaced Repetition Scheduler*), que entrou no Anki em 23.10 e passou a ser o
recomendado nas versões seguintes. Ficou o FSRS, por três razões, e a terceira é a que decide para
**táticas**:

1. **O SM-2 não modela esquecimento; ele multiplica.** O estado dele é um *fator de facilidade* e o
   intervalo seguinte é `intervalo × fator`. Não há noção de "qual é a chance de eu ainda lembrar
   disto hoje", então não há como pedir uma **retenção alvo** -- e é justamente o botão que um
   profissional quer: *"quero acertar 90% do que revejo"* é uma frase que só o FSRS sabe responder,
   porque o modelo dele é uma curva de esquecimento explícita (ver `retencao`).
2. **A escala de tempo do SM-2 é a repetição, não o calendário.** Ele não usa quanto tempo passou
   de verdade: dois acertos com um dia e com um ano de intervalo mexem o fator igual. O FSRS come a
   retrievabilidade do momento (`R`) nas duas fórmulas de estabilidade -- e é por isso que
   **sumir por um mês** tem tratamento nativo aqui, e não uma regra especial: ver `proximo`.
3. **O "inferno de facilidade" do SM-2 é o modo de falha das táticas.** Cada erro tira 0,2 do fator,
   e o piso é 1,3; um acerto devolve quase nada. Numa coleção de combinações, em que errar é o caso
   normal nas primeiras voltas, metade dos itens desce ao piso e **nunca sobe**: o intervalo trava
   em 1,3× para sempre e o baralho vira uma fila diária que não encolhe. O FSRS separa
   *dificuldade* de *estabilidade*, e o item difícil continua ganhando intervalo quando é acertado.

**O preço, e ele é dito em voz alta: dezessete pesos que este projeto não derivou.** `PESOS` são os
padrões publicados do FSRS-4.5, copiados. A graça do FSRS é poder **otimizá-los** contra o histórico
de quem usa, e otimizá-los aqui exigiria um histórico que ainda não existe nesta máquina. É por isso
que `Estado` guarda o log inteiro de revisões em vez de só a última: ele é a entrada do otimizador
do dia em que houver o que otimizar, e jogá-lo fora agora fecharia a porta.

## O que não é do algoritmo, e mesmo assim decide o dia

O FSRS diz **quando** cada item vence. Ele não diz o que fazer quando 400 vencem juntos, e é isso
que acontece com quem some por um mês. Os dois tetos de `Agenda` são a resposta -- `TETO_DO_DIA` e
`TETO_DE_NOVOS` --, e a **ordem** dentro do dia é a outra metade: a fila sai pela retenção estimada,
do mais perdido para o menos, e não pela data. Ver `agenda`.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Any

__all__ = [
    "BOM",
    "DECAY",
    "DE_NOVO",
    "DIFICIL",
    "DIFICULDADE_MAXIMA",
    "DIFICULDADE_MINIMA",
    "ESTABILIDADE_MINIMA",
    "FACIL",
    "FATOR",
    "NOTAS",
    "PESOS",
    "RETENCAO_ALVO",
    "TETO_DE_INTERVALO",
    "TETO_DE_NOVOS",
    "TETO_DO_DIA",
    "Agenda",
    "Estado",
    "Revisao",
    "agenda",
    "atrasados",
    "estado_inicial",
    "intervalo",
    "nota_do_treino",
    "proximo",
    "retencao",
    "rotulo_da_nota",
]

# ------------------------------------------------------------------------------- as notas

DE_NOVO = 1
DIFICIL = 2
BOM = 3
FACIL = 4
"""As quatro notas do FSRS, na numeração dele. Inteiros e não texto porque são índice de `PESOS`."""

NOTAS: tuple[int, ...] = (DE_NOVO, DIFICIL, BOM, FACIL)

_ROTULOS: dict[int, str] = {
    DE_NOVO: "de novo",
    DIFICIL: "difícil",
    BOM: "bom",
    FACIL: "fácil",
}


def rotulo_da_nota(nota: int) -> str:
    """Como a nota se escreve nos quatro botões. Nota fora da escala devolve vazio."""
    return _ROTULOS.get(int(nota), "")


# ------------------------------------------------------------------------------ os pesos

PESOS: tuple[float, ...] = (
    0.4872, 1.4003, 3.7145, 13.8206, 5.1618, 1.2298, 0.8975, 0.0310,
    1.6474, 0.1367, 1.0461, 2.1072, 0.0793, 0.3246, 1.5870, 0.2272, 2.8755,
)
"""Os dezessete pesos publicados do FSRS-4.5, **copiados e não derivados aqui** (S-540).

Os quatro primeiros são a estabilidade inicial de cada nota, em dias: errar de saída vale ~0,5 dia
e acertar de primeira com facilidade vale ~13,8. O resto governa a dificuldade (`w4`, `w5`, `w6`,
`w7`), o ganho de estabilidade no acerto (`w8` a `w10`), a perda no erro (`w11` a `w14`) e os dois
ajustes de nota (`w15` para *difícil*, `w16` para *fácil*).

**Um peso errado aqui não quebra nada visivelmente**, e é por isso que o aviso está escrito: o
agendamento continua monotônico e plausível, só deixa de ser o do artigo. Quem quiser conferi-los
compara com o `open-spaced-repetition/fsrs4anki`; quem quiser **melhorá-los** precisa de um
histórico de revisão, que é exatamente o que `Estado.historico` guarda."""

DECAY = -0.5
FATOR = 0.9 ** (1.0 / DECAY) - 1.0
"""A curva de esquecimento do FSRS-4.5: `R(t) = (1 + FATOR·t/S)^DECAY`.

`FATOR` é derivado de `DECAY` e **não** escrito à mão: os dois juntos são o que faz `t = S` dar
exatamente 90% de retenção, que é a definição de estabilidade. Escrever `0.9` aqui como terceira
constante seria a chance de os três discordarem."""

RETENCAO_ALVO = 0.90
"""A chance de acerto que o intervalo persegue. Noventa por cento é o padrão do Anki, e o número tem
significado direto: com ele, o intervalo **é** a estabilidade (ver `FATOR`).

Mais alto pede mais revisões pelo mesmo material; mais baixo esquece mais. É parâmetro de `agenda`
e de `intervalo`, e não constante fechada, porque é a única perilla que faz sentido oferecer."""

DIFICULDADE_MINIMA = 1.0
DIFICULDADE_MAXIMA = 10.0
ESTABILIDADE_MINIMA = 0.1
"""Meio dia arredondado para baixo: abaixo disso o intervalo seria fração de hora, e este programa
agenda por **dia** -- não há sessão de revisão de quinze minutos num livro de xadrez."""

TETO_DE_INTERVALO = 3650
"""Dez anos. Não é opinião sobre memória: é o ponto em que "revise isto" deixa de ser um plano."""

TETO_DO_DIA = 60
"""Quantos itens vencidos a agenda oferece por dia, no máximo (S-540).

**É o que impede que sumir por um mês vire uma parede.** Trezentos itens vencidos numa tela não são
uma sessão de treino: são o motivo pelo qual as pessoas abandonam repetição espaçada. Sessenta
táticas a ~40 s cada dão ~40 min, que é a sessão de treino que um profissional encaixa num dia. O
resto continua vencido e volta amanhã, na ordem de quem está mais perdido."""

TETO_DE_NOVOS = 15
"""E quantos itens **nunca vistos** entram por dia. Menor que o teto de vencidos de propósito: item
novo custa mais atenção que revisão, e cada novo de hoje é revisão de amanhã -- um baralho que
admite cem novos por dia produz a parede acima em duas semanas."""


# --------------------------------------------------------------------------------- o estado


@dataclass(frozen=True)
class Revisao:
    """Uma revisão que aconteceu. É o log que o otimizador do FSRS come.

    Três campos e não um: a nota sozinha não diz nada sem **quanto tempo tinha passado**, que é a
    variável que o SM-2 ignora e o FSRS usa.
    """

    dia: date
    nota: int
    dias: int = 0
    """Dias decorridos desde a revisão anterior. Zero na primeira."""

    def para_json(self) -> dict[str, Any]:
        return {"dia": self.dia.isoformat(), "nota": int(self.nota), "dias": int(self.dias)}

    @classmethod
    def de_json(cls, dados: Any) -> Revisao:
        bruto = dados if isinstance(dados, dict) else {}
        return cls(
            dia=date.fromisoformat(str(bruto.get("dia", date.min.isoformat()))),
            nota=int(bruto.get("nota", BOM)),
            dias=int(bruto.get("dias", 0)),
        )


@dataclass(frozen=True)
class Estado:
    """O que se sabe de um item agendado: estabilidade, dificuldade, vencimento e o log.

    **Estabilidade e dificuldade são coisas diferentes, e é a separação que o SM-2 não tem.**
    Estabilidade é *quanto tempo isto dura na memória*, em dias; dificuldade é *quão duro este item
    é*, de 1 a 10. Um item difícil ganha intervalo mais devagar, mas ganha -- e é isso que impede o
    inferno de facilidade descrito no cabeçalho.
    """

    chave: str
    estabilidade: float = 0.0
    dificuldade: float = 0.0
    vencimento: date | None = None
    """Quando ele volta. `None` = nunca foi visto, e é o que `agenda` chama de novo."""

    ultima: date | None = None
    revisoes: int = 0
    lapsos: int = 0
    historico: tuple[Revisao, ...] = field(default_factory=tuple)

    @property
    def novo(self) -> bool:
        return self.vencimento is None

    def vencido_em(self, hoje: date) -> bool:
        return self.vencimento is not None and self.vencimento <= hoje

    def dias_desde(self, hoje: date) -> int:
        """Dias decorridos desde a última revisão. Zero para item novo e para data no futuro."""
        if self.ultima is None:
            return 0
        return max(0, (hoje - self.ultima).days)

    def retencao_em(self, hoje: date) -> float:
        """A chance estimada de acertar este item hoje. Item novo vale zero -- não há o que lembrar."""
        if self.vencimento is None or self.estabilidade <= 0:
            return 0.0
        return retencao(self.dias_desde(hoje), self.estabilidade)

    def para_json(self) -> dict[str, Any]:
        return {
            "chave": self.chave,
            "estabilidade": round(float(self.estabilidade), 4),
            "dificuldade": round(float(self.dificuldade), 4),
            "vencimento": self.vencimento.isoformat() if self.vencimento else None,
            "ultima": self.ultima.isoformat() if self.ultima else None,
            "revisoes": int(self.revisoes),
            "lapsos": int(self.lapsos),
            "historico": [r.para_json() for r in self.historico],
        }

    @classmethod
    def de_json(cls, dados: Any) -> Estado:
        bruto = dados if isinstance(dados, dict) else {}
        vencimento = bruto.get("vencimento")
        ultima = bruto.get("ultima")
        return cls(
            chave=str(bruto.get("chave", "")),
            estabilidade=float(bruto.get("estabilidade", 0.0)),
            dificuldade=float(bruto.get("dificuldade", 0.0)),
            vencimento=date.fromisoformat(str(vencimento)) if vencimento else None,
            ultima=date.fromisoformat(str(ultima)) if ultima else None,
            revisoes=int(bruto.get("revisoes", 0)),
            lapsos=int(bruto.get("lapsos", 0)),
            historico=tuple(Revisao.de_json(r) for r in bruto.get("historico", ())),
        )


# ---------------------------------------------------------------------------- o algoritmo


def retencao(dias: float, estabilidade: float) -> float:
    """A chance de ainda lembrar depois de `dias`, com aquela estabilidade (FSRS-4.5).

    `R(t) = (1 + FATOR·t/S)^DECAY` -- a curva **de potência**, e não a exponencial do SM-2 e do
    Ebbinghaus de manual. A diferença aparece na cauda: a exponencial diz que um item de
    estabilidade 10 dias está praticamente perdido em 60, e a medição de milhões de revisões do
    Anki diz que ele não está. É a mudança que o FSRS-4.5 trouxe sobre o 4.
    """
    s = max(ESTABILIDADE_MINIMA, float(estabilidade))
    return float((1.0 + FATOR * max(0.0, float(dias)) / s) ** DECAY)


def intervalo(estabilidade: float, *, alvo: float = RETENCAO_ALVO) -> int:
    """Quantos dias até a retenção cair para `alvo`. Arredondado, nunca abaixo de um dia.

    É a inversa de `retencao`, e é por ela que a retenção alvo vira um botão de verdade: pedir 95%
    encurta todos os intervalos de uma vez, sem mexer em nada do que já foi aprendido.
    """
    limpo = min(0.999, max(0.001, float(alvo)))
    s = max(ESTABILIDADE_MINIMA, float(estabilidade))
    dias = s / FATOR * (limpo ** (1.0 / DECAY) - 1.0)
    return int(max(1, min(TETO_DE_INTERVALO, round(dias))))


def _dificuldade_inicial(nota: int) -> float:
    return _limitar(
        PESOS[4] - math.exp(PESOS[5] * (int(nota) - 1)) + 1.0,
        DIFICULDADE_MINIMA,
        DIFICULDADE_MAXIMA,
    )


def _limitar(valor: float, minimo: float, maximo: float) -> float:
    return float(min(maximo, max(minimo, valor)))


def estado_inicial(chave: str, nota: int, *, hoje: date, alvo: float = RETENCAO_ALVO) -> Estado:
    """O estado de um item visto pela primeira vez.

    A estabilidade inicial é o peso da nota -- `w0` a `w3` --, e é aqui que se vê o desenho do
    FSRS: errar de saída não zera o item, dá a ele ~meio dia; acertar com facilidade dá quase duas
    semanas **sem passar pelos degraus de aprendizado** que o SM-2 obriga.
    """
    grau = _nota_valida(nota)
    estabilidade = max(ESTABILIDADE_MINIMA, float(PESOS[grau - 1]))
    return Estado(
        chave=str(chave),
        estabilidade=estabilidade,
        dificuldade=_dificuldade_inicial(grau),
        vencimento=hoje + timedelta(days=intervalo(estabilidade, alvo=alvo)),
        ultima=hoje,
        revisoes=1,
        lapsos=1 if grau == DE_NOVO else 0,
        historico=(Revisao(dia=hoje, nota=grau, dias=0),),
    )


def _nota_valida(nota: int) -> int:
    valor = int(nota)
    if valor not in NOTAS:
        raise ValueError(f"nota fora da escala do FSRS: {nota!r}. As válidas estão em NOTAS.")
    return valor


def proximo(estado: Estado, nota: int, *, hoje: date, alvo: float = RETENCAO_ALVO) -> Estado:
    """O estado depois de mais uma revisão. Item novo cai em `estado_inicial` (S-540).

    **É aqui que sumir por um mês tem resposta, e ela não é uma regra à parte.** Os dias decorridos
    entram por `R` -- a retenção que o item tinha no momento em que foi revisto --, e `R` está nas
    duas fórmulas de estabilidade com o mesmo sinal: quanto **mais** perdido o item estava, maior o
    ganho de um acerto e menor a perda de um erro. Lembrar de algo que se tinha 40% de chance de
    lembrar prova mais que lembrar do que se sabia de cor, e o modelo diz isso em uma linha.

    **O erro nunca aumenta a estabilidade**, e a trava é explícita (`min(..., S)`): a fórmula de
    lapso do FSRS-4.5 pode devolver mais que a estabilidade anterior em item de estabilidade muito
    baixa, e um item que se acabou de errar não pode ficar mais firme por isso.
    """
    if estado.vencimento is None or estado.estabilidade <= 0:
        return replace(estado_inicial(estado.chave, nota, hoje=hoje, alvo=alvo), chave=estado.chave)

    grau = _nota_valida(nota)
    dias = estado.dias_desde(hoje)
    r = retencao(dias, estado.estabilidade)
    dificuldade = _proxima_dificuldade(estado.dificuldade, grau)
    if grau == DE_NOVO:
        estabilidade = min(estado.estabilidade, _estabilidade_no_lapso(estado, dificuldade, r))
    else:
        estabilidade = _estabilidade_no_acerto(estado, dificuldade, r, grau)
    estabilidade = max(ESTABILIDADE_MINIMA, estabilidade)
    return Estado(
        chave=estado.chave,
        estabilidade=estabilidade,
        dificuldade=dificuldade,
        vencimento=hoje + timedelta(days=intervalo(estabilidade, alvo=alvo)),
        ultima=hoje,
        revisoes=estado.revisoes + 1,
        lapsos=estado.lapsos + (1 if grau == DE_NOVO else 0),
        historico=(*estado.historico, Revisao(dia=hoje, nota=grau, dias=dias)),
    )


def _proxima_dificuldade(dificuldade: float, nota: int) -> float:
    """A dificuldade nova, com a **reversão à média** que o FSRS aplica (`w7`).

    Sem ela, uma sequência de acertos levaria todo item ao mínimo e o modelo perderia a memória de
    que aquele item já foi duro. A reversão puxa devagar para a dificuldade de um item acertado com
    facilidade, que é o "fácil por natureza".
    """
    andou = dificuldade - PESOS[6] * (nota - BOM)
    revertida = PESOS[7] * _dificuldade_inicial(FACIL) + (1.0 - PESOS[7]) * andou
    return _limitar(revertida, DIFICULDADE_MINIMA, DIFICULDADE_MAXIMA)


def _estabilidade_no_acerto(estado: Estado, dificuldade: float, r: float, nota: int) -> float:
    penalidade = PESOS[15] if nota == DIFICIL else 1.0
    bonus = PESOS[16] if nota == FACIL else 1.0
    ganho = (
        math.exp(PESOS[8])
        * (11.0 - dificuldade)
        * (estado.estabilidade ** -PESOS[9])
        * (math.exp(PESOS[10] * (1.0 - r)) - 1.0)
        * penalidade
        * bonus
    )
    return float(estado.estabilidade * (1.0 + ganho))


def _estabilidade_no_lapso(estado: Estado, dificuldade: float, r: float) -> float:
    return float(
        PESOS[11]
        * (dificuldade ** -PESOS[12])
        * ((estado.estabilidade + 1.0) ** PESOS[13] - 1.0)
        * math.exp(PESOS[14] * (1.0 - r))
    )


# ------------------------------------------------------------------- a nota que o treino dá


def nota_do_treino(*, certo: bool, tentativas: int = 1, viu_a_solucao: bool = False) -> int:
    """A nota do FSRS a partir do que aconteceu no tabuleiro (S-540).

    **A tradução é do produto e não do algoritmo**, e por isso ela mora aqui e não no painel: os
    quatro botões do Anki pedem que a pessoa julgue a própria memória, e num exercício de tática
    isso já está medido -- ou o lance saiu, ou não saiu.

    - **errou, ou pediu para ver a solução** → `DE_NOVO`. Ver a resposta é não saber a resposta.
    - **acertou na primeira** → `BOM`. É o caso normal, e é o que o Anki chama de "bom".
    - **acertou depois de errar** → `DIFICIL`. O item ainda entra na conta como acerto -- errar e
      corrigir não é o mesmo que não achar --, mas ganha o multiplicador de penalidade (`w15`).
    - **`FACIL` não é dado pelo programa, e isso é decisão.** Ele multiplica a estabilidade por
      `w16` e produz intervalos muito longos; concedê-lo automaticamente a todo acerto de primeira
      esvaziaria a fila com base numa inferência que ninguém fez. É o botão que a pessoa aperta.
    """
    if not certo or viu_a_solucao:
        return DE_NOVO
    return BOM if int(tentativas) <= 1 else DIFICIL


# ---------------------------------------------------------------------------- a agenda do dia


@dataclass(frozen=True)
class Agenda:
    """A fila de hoje, já cortada pelos dois tetos, e a conta do que ficou de fora."""

    fila: tuple[str, ...] = ()
    """As chaves na ordem em que devem ser mostradas. Vencidos primeiro, novos depois."""

    vencidos: int = 0
    """Quantos itens estão vencidos no total -- inclusive os que não couberam no teto."""

    novos: int = 0
    """Quantos itens nunca vistos existem no baralho."""

    adiados: int = 0
    """Vencidos que não couberam hoje. É o número que a tela precisa dizer em voz alta."""

    @property
    def quantos(self) -> int:
        return len(self.fila)

    @property
    def vazia(self) -> bool:
        return not self.fila


def atrasados(estados: Iterable[Estado], hoje: date) -> list[Estado]:
    """Os itens vencidos, **do mais perdido para o menos** (S-540).

    A ordem é por retenção estimada, e não por data de vencimento, e a diferença aparece
    exatamente quando ela importa -- num acúmulo. Dois itens vencidos há dez dias: um tinha
    intervalo de três dias e o outro de duzentos. O primeiro já foi esquecido; o segundo está
    praticamente intacto. Ordenar pela data trataria os dois igual e gastaria a sessão de hoje no
    que não corria risco.

    Empate desfeito pela chave, para a fila ser a mesma em duas chamadas do mesmo dia -- uma fila
    que se embaralha entre dois desenhos da tela é uma fila em que a pessoa perde o lugar.
    """
    vencidos = [estado for estado in estados if estado.vencido_em(hoje)]
    return sorted(vencidos, key=lambda estado: (estado.retencao_em(hoje), estado.chave))


def agenda(
    chaves: Sequence[str],
    estados: Mapping[str, Estado],
    *,
    hoje: date,
    teto: int = TETO_DO_DIA,
    novos: int = TETO_DE_NOVOS,
) -> Agenda:
    """A fila de hoje: os vencidos que cabem, e depois os novos que cabem (S-540).

    **Vencidos antes de novos, sempre.** Aprender coisa nova enquanto o que já se aprendeu está
    sendo esquecido é o jeito de ter um baralho grande e uma memória pequena; é a ordem do Anki, e
    pela mesma razão.

    `chaves` é o universo -- os exercícios extraídos e os estudos da sala --, e `estados` é o que
    já foi revisto. Chave sem estado é item novo. **Estado sem chave é ignorado em silêncio**: é o
    exercício de um livro que saiu da pasta, e derrubar a agenda do dia por causa dele seria trocar
    a sessão de treino por uma mensagem de erro.
    """
    conhecidas = list(dict.fromkeys(str(chave) for chave in chaves))
    vistos = [estados[chave] for chave in conhecidas if chave in estados]
    novas = [chave for chave in conhecidas if chave not in estados]

    devidos = atrasados(vistos, hoje)
    cabem = max(0, int(teto))
    fila = [estado.chave for estado in devidos[:cabem]]
    sobra = max(0, cabem - len(fila))
    fila += novas[: min(sobra, max(0, int(novos)))]
    return Agenda(
        fila=tuple(fila),
        vencidos=len(devidos),
        novos=len(novas),
        adiados=max(0, len(devidos) - cabem),
    )
