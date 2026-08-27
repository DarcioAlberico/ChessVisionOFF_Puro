"""O documento do editor como dado, e não como tag do widget (S-235).

**O defeito que este módulo existe para impedir.** O que a aba de texto entrega quando alguém salva
é uma `str` -- `self.editor.get("1.0", "end-1c")` --, e tudo o mais que está na tela fica de fora: as
tags de faixa, o negrito que a S-237 acabou de trazer da camada, as miniaturas. Enquanto a aba não
tinha formatação, isso era barato. Deixa de ser no primeiro recurso de edição: um
`tag_configure("negrito", font=...)` resolve o negrito **na tela** em quatro linhas e entrega, no
botão Salvar, exatamente o mesmo `.txt` de antes.

E o defeito não apareceria em teste de interface nenhum, porque na tela está tudo certo. Apareceria
no arquivo de quem passou a tarde corrigindo uma página.

**Tag do Tk não é dado: ela nasce no widget, vive no widget e morre com ele.** Este módulo é o outro
lado -- o documento que sobrevive ao widget, sem `import tkinter`, na mesma regra que pôs
`text/documento.py` fora da janela.

## A corrida, e por que ela carrega quatro coisas que não são texto

Uma `Corrida` é um trecho contíguo de texto com os mesmos atributos. Além deles ela carrega:

    faixa          a régua de confiança, que é de outro dono (text/documento.py)
    bloco          de que bloco da PaginaLida ela saiu -- SEM_BLOCO quando foi escrita à mão
    procedencia    quem leu aquilo: camada, glifo, rapidocr, humano -- ou None
    tipo           texto, diagrama ou separador

**`faixa` não entra em `Atributos`, e essa fronteira é o item.** Confiança é medida do
reconhecimento; atributo é escolha de quem escreve. Num campo só, "pintar de vermelho" e "o motor
adivinhou" seriam a mesma informação -- e é a colisão que a S-242 vai ter de desfazer canal a canal.

**`bloco` é o que torna a correção aproveitável.** Sem ele, corrigir uma palavra não tem como dizer
*sobre que bloco* a correção foi feita, e a S-239 não tem o que entregar à fila da S-212.

## Duas decisões que a implementação virou, e as duas divergem do desenho da spec

1. **`procedencia` é `Procedencia | None`, e não `"humano"` por padrão.** O separador entre dois
   blocos não foi lido por ninguém e não foi escrito por ninguém: dizer que ele é humano seria
   inventar autoria de uma linha em branco. `None` é "não veio de leitura", que é o mesmo idioma do
   `LinhaLida.negrito` da S-237 -- e quem carimba `"humano"` de fato é a S-239, no momento em que a
   edição acontece.

2. **`cor` e `estilo` nasceram com o registro vazio, e deixaram de nascer.** Na S-235 os dois eram
   campos reais e validados cujo único valor válido era `""`, pela decisão do `Comando.icone` da
   S-219: o campo existe e recusa nome que ninguém desenhou. A S-242 povoou `CORES_DE_AUTOR` (e
   acrescentou `realce`, que é o canal do autor), a S-249 povoou `ESTILOS`, e a S-247 acrescentou
   `fora_do_modelo`. A trava continua igual dos dois lados: nome fora do registro levanta, e nome
   no registro sem quem o desenhe é reprovado por `tests/test_texto_rico.py`.

## A edição, e por que ela mora aqui

Da S-241 em diante este módulo deixou de ser só uma estrutura e passou a ter **verbos**:
`alternar`, `aplicar`, `aplicar_no_paragrafo`, `mudar_corpo`, `mudar_caixa`, `inserir`,
`substituir_intervalo`. Todos são puros, todos falam em **deslocamento de caractere** -- e nenhum
sabe o que é um índice do Tk.

Eles se dividem em três, e a divisão decide o que o painel faz depois de chamar cada um:

    do trecho       alternar, aplicar, limpar_formato, limpar_cor, mudar_corpo
    do parágrafo    aplicar_no_paragrafo -- e com ela aplicar_estilo e aplicar_alinhamento
    do texto        mudar_caixa, substituir_intervalo, inserir

Os dois primeiros grupos não mudam um caractere, e o painel os desenha por etiqueta, sem redesenhar.
O terceiro muda, e ali o painel guarda um instantâneo antes -- porque o redesenho zera a pilha de
desfazer do Tk. É a fronteira que o cabeçalho de `ui/texto_panel.py` explica do outro lado.

É essa fronteira que faz o editor ser testável: o painel converte `"sel.first"` em deslocamento,
chama a função e redesenha. A conversão é o único pedaço que precisa do widget, e ela é pequena por
construção. Um `tag_add` na seleção resolveria o negrito **na tela** em quatro linhas e entregaria,
no botão Salvar, exatamente o `.txt` de antes -- que é o achado 1 do ROADMAP_EDITOR.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, fields, replace
from typing import Any, get_args

from . import documento, notacao
from .pagina import PaginaLida, Procedencia

SEM_BLOCO = -1
"""O `bloco` de uma corrida que não saiu da página: texto escrito à mão.

Não é `None` porque o campo é índice, e um índice ausente que se compara com `is None` num laço de
edição é uma condição a mais em todo lugar que o lê. `-1` nunca é índice válido de `PaginaLida.blocos`."""

TEXTO = "texto"
DIAGRAMA = "diagrama"
SEPARADOR = "separador"
TIPOS: tuple[str, ...] = (TEXTO, DIAGRAMA, SEPARADOR)
"""Os mesmos três de `documento.Segmento.tipo`, e o conjunto é fechado.

Fechado porque `para_texto` e a fusão dependem dele: uma corrida de tipo desconhecido não tem como
saber se pode ser fundida com a vizinha nem o que o exportador deve fazer com ela."""

PROCEDENCIAS: tuple[str, ...] = get_args(Procedencia)
"""As quatro de `text/pagina.py`, **derivadas do `Literal`** e não recopiadas.

Copiar a lista aqui seria a segunda declaração do mesmo conjunto -- e a que ficaria para trás no dia
em que uma quinta procedência entrasse."""

CORES_DE_AUTOR: tuple[str, ...] = ("destaque", "citacao", "nota", "variante")
"""Os nomes de cor que o autor pode aplicar, nos dois canais -- letra (`cor`) e fundo (`realce`).

**São nomes, e nunca hexadecimal nem papel de `ui/tokens.py`.** O domínio nomeia o conceito e a
interface o resolve em cor -- é o que `PAPEL_DA_FAIXA` já faz com `revisar` e `conferir`, e é o que
mantém este módulo sem saber que existe uma janela.

**Os nomes dizem o que o autor quis marcar, e nenhum deles fala de confiança.** "destaque",
"citação", "nota" e "variante" são intenções de quem escreve; "duvidoso" ou "erro" seriam a língua
da faixa dita por outra boca, e é exatamente isso que a S-242 proíbe. A S-242 decidiu o canal: a cor da
letra já diz confiança nesta aba (`revisar` em `tokens.PROBLEMA`, `conferir` em `tokens.ATENCAO`), e
uma cor de autor que falasse a mesma língua produziria duas tintas iguais com dois significados na
mesma linha. Quem garante a separação é `ui/texto_cores.py`, que mapeia estes quatro nomes a papéis
**disjuntos** dos da faixa -- e o teste afirma a interseção vazia."""

ESTILO_TITULO = "titulo"
ESTILO_PROSA = "prosa"
ESTILO_NOTACAO = "notacao"
ESTILO_LEGENDA = "legenda"

ESTILOS: tuple[str, ...] = (ESTILO_TITULO, ESTILO_PROSA, ESTILO_NOTACAO, ESTILO_LEGENDA)
"""Os estilos de parágrafo da S-249, e o conjunto é fechado como `GRUPOS` em `ui/comandos.py`.

Cada um tem um dono na página lida -- tarja vira título, bloco recuado vira prosa, a linha atada a
um diagrama vira legenda --, e `notacao` é o único **sem** derivação automática: o corte que separa
uma linha de lances de uma linha de prosa não foi medido, e a regra 5 da SPEC_EDITOR manda entregar
o pincel manual em vez de pintar palpite."""

ALINHAMENTO_ESQUERDA = "esquerda"
ALINHAMENTO_CENTRO = "centro"
ALINHAMENTO_DIREITA = "direita"
ALINHAMENTO_JUSTIFICADO = "justificado"

ALINHAMENTOS: tuple[str, ...] = (
    ALINHAMENTO_ESQUERDA,
    ALINHAMENTO_CENTRO,
    ALINHAMENTO_DIREITA,
    ALINHAMENTO_JUSTIFICADO,
)
"""Onde o parágrafo se apoia na coluna (S-259). Conjunto fechado como `ESTILOS`.

**`""` e `esquerda` não são a mesma coisa, e a diferença é a de quem escolheu.** `""` é o parágrafo
que ninguém alinhou -- ele se desenha à esquerda porque é assim que texto se desenha, e a página o
entregou assim. `esquerda` é uma escolha: alguém centralizou e voltou atrás, e essa decisão
sobrevive ao arquivo em vez de virar indistinguível do que nunca foi tocado. É a mesma fronteira que
`cor` mantém entre "sem cor" e "cor que o autor escolheu"."""

CORPO_MINIMO = -3
CORPO_MAXIMO = 6
"""Os limites do degrau de corpo (S-260). **A faixa é curta, e os dois lados têm razão diferente.**

Embaixo, o piso é de legibilidade e ele é de `ui/tipografia.MINIMO_LEGIVEL`: −3 sobre a Segoe UI 9
já chega em 6, e o módulo da escala não deixa passar de 7. Encurtar mais aqui seria repetir aquela
decisão num segundo lugar; deixar aberto faria a interface oferecer um degrau que a fonte recusa.

Em cima, o teto é do editor: esta aba desenha uma folha de livro, e um trecho oito pontos maior que
o resto não é ênfase -- é outro documento. Seis degraus cobrem de legenda a título de capítulo."""


def corpo_no_limite(degrau: int) -> int:
    """O degrau grampeado na faixa. É o que todo comando de corpo chama antes de escrever.

    Grampear e não levantar, **aqui**: quem aperta "aumentar" oito vezes num trecho que já está no
    teto está pedindo o teto, e não um erro. Quem levanta é `Atributos`, sobre um valor que veio de
    fora do gesto -- ver o `__post_init__`."""
    return max(CORPO_MINIMO, min(CORPO_MAXIMO, int(degrau)))


CAIXA_ALTA = "alta"
CAIXA_BAIXA = "baixa"
CAIXA_INICIAIS = "iniciais"

CAIXAS: tuple[str, ...] = (CAIXA_ALTA, CAIXA_BAIXA, CAIXA_INICIAIS)
"""As três trocas de caixa (S-262). **Não são atributo**: elas mudam o texto, e não como ele é
desenhado -- por isso não há campo em `Atributos` para elas, e por isso `mudar_caixa` devolve
documento com texto novo, no caminho que a substituição em massa já usa."""


@dataclass(frozen=True)
class Atributos:
    """Como um trecho é desenhado. Só o que o autor escolhe -- confiança não mora aqui."""

    negrito: bool = False
    italico: bool = False
    sublinhado: bool = False
    tachado: bool = False
    """A linha que corta o trecho (S-261) -- o quarto da ênfase, e o único que **retira**.

    Negrito, itálico e sublinhado dizem "olhe para isto"; o tachado diz "isto sai". Numa aba cuja
    matéria é OCR corrigido, é a marca de quem já decidiu que um trecho é lixo de leitura e ainda não
    quer apagá-lo -- apagar é irreversível depois do próximo redesenho, e riscar não é."""

    cor: str = ""
    """Nome em `CORES_DE_AUTOR`, aplicado à **letra**. `""` é "sem cor de autor"."""

    realce: str = ""
    """Nome em `CORES_DE_AUTOR`, aplicado ao **fundo** -- o canal do autor (S-242).

    Separado de `cor` porque os dois canais dizem coisas diferentes nesta aba: a letra já carrega a
    faixa de confiança, e o realce é o canal livre. Um campo só, com um interruptor "é fundo?", faria
    a mesma escolha caber em dois lugares e obrigaria quem lê o documento a perguntar qual valia."""

    estilo: str = ""
    """Nome em `ESTILOS` -- o atributo do **parágrafo**, e não do trecho (S-249).

    Mora aqui, e não numa segunda estrutura de parágrafo, porque o documento não tem parágrafo: tem
    corridas. O estilo é o mesmo em todas as corridas de um parágrafo, e quem o aplica escreve nas
    corridas do intervalo inteiro -- ver `aplicar_estilo`."""

    alinhamento: str = ""
    """Nome em `ALINHAMENTOS` -- atributo do **parágrafo**, como `estilo` (S-259).

    Mora aqui pela mesma razão que `estilo` mora: o documento não tem parágrafo, tem corridas, e o
    parágrafo é o conjunto de corridas do mesmo bloco. Quem o aplica escreve nas corridas do bloco
    inteiro -- ver `aplicar_alinhamento`.

    **É o único atributo que a marca do diagrama aceita**, e é o que faz "centralizar a figura" ser a
    mesma escolha que "centralizar o parágrafo" em vez de um segundo mecanismo ao lado. Ver
    `ATRIBUTOS_DA_MARCA`."""

    corpo: int = 0
    """Quantos degraus **acima ou abaixo** do corpo que aquele trecho teria (S-260).

    Degrau, e nunca ponto nem pixel: quem transforma isto em tamanho é `ui/tipografia.corpo`, sobre
    a fonte do sistema. Um `12` cravado aqui ignoraria quem aumentou a fonte do Windows -- a regra 3
    da SPEC_EDITOR, e o mesmo defeito que `PAPEL_DO_ESTILO` evita do outro lado.

    `0` é "o corpo do estilo deste parágrafo", e é por isso que ele soma em vez de substituir: um
    trecho de título com `+1` continua sendo título, um degrau maior."""

    fora_do_modelo: bool = False
    """Este trecho traz símbolo que **nenhuma classe do modelo pode confirmar** (S-247).

    Não é defeito nem aviso: é declaração. Quem escreve prosa própria insere `♞` e segue a vida; a
    marca existe para quem depois perguntar *"isto veio da página?"* -- e para a S-212 não tratar
    como leitura corrigida um caractere que leitura nenhuma produziu."""

    def __post_init__(self) -> None:
        # Levanta em vez de cair no vazio, pela razão de `estilos.estilo_de_botao`: um nome escrito
        # errado que virasse "sem cor" é exatamente o estado que este campo veio impedir, e ele
        # voltaria sem ninguém notar.
        for campo, valor in (("cor", self.cor), ("realce", self.realce)):
            if valor and valor not in CORES_DE_AUTOR:
                raise KeyError(f"{campo} de autor desconhecido: {valor!r}. Os válidos estão em CORES_DE_AUTOR.")
        if self.estilo and self.estilo not in ESTILOS:
            raise KeyError(f"estilo desconhecido: {self.estilo!r}. Os válidos estão em ESTILOS.")
        if self.alinhamento and self.alinhamento not in ALINHAMENTOS:
            raise KeyError(
                f"alinhamento desconhecido: {self.alinhamento!r}. Os válidos estão em ALINHAMENTOS."
            )
        # **Levanta, e não grampeia.** Quem grampeia é `corpo_no_limite`, no gesto -- ali um degrau
        # a mais é o pedido de quem apertou o botão pela sétima vez. Aqui o valor veio de um arquivo
        # ou de uma etiqueta, e um `corpo=40` que virasse 6 em silêncio seria um documento que se
        # abre diferente do que foi gravado sem nada dizer. Quem perdoa é `texto_etiquetas`, no
        # caminho de salvar, onde recusar custaria o trabalho da tarde.
        if not CORPO_MINIMO <= self.corpo <= CORPO_MAXIMO:
            raise KeyError(
                f"degrau de corpo fora da faixa: {self.corpo!r}. "
                f"O válido vai de {CORPO_MINIMO} a {CORPO_MAXIMO}."
            )

    @property
    def padrao(self) -> bool:
        """Nada foi escolhido neste trecho. É o que a fusão e a serialização perguntam."""
        return self == PADRAO

    def para_json(self) -> dict[str, Any]:
        """Só o que difere do padrão.

        **O arquivo não guarda os cinco campos de todo trecho**, e não é economia de bytes: é o que
        faz um campo novo -- a cor da S-242, o estilo da S-249 -- entrar sem mudar uma linha dos
        arquivos já gravados. Quem lê preenche o resto com o padrão."""
        atual = {campo.name: getattr(self, campo.name) for campo in fields(self)}
        return {nome: valor for nome, valor in atual.items() if valor != getattr(PADRAO, nome)}

    @classmethod
    def de_json(cls, dados: Any) -> Atributos:
        """O que o arquivo trouxer, e o padrão para o resto. Chave desconhecida é ignorada.

        Ignorada e não recusada porque o caso é um arquivo gravado por uma versão **mais nova**, que
        conhece um atributo que esta não conhece: abrir o texto sem aquele atributo é melhor que
        recusar o arquivo inteiro. Quem recusa versão futura é o formato da S-238, que tem o número
        para comparar -- aqui não há."""
        if not isinstance(dados, dict):
            return PADRAO
        conhecidos = {campo.name for campo in fields(cls)}
        return cls(**{nome: valor for nome, valor in dados.items() if nome in conhecidos})


PADRAO = Atributos()
"""O trecho sem escolha nenhuma. Instância única para a comparação da fusão ser barata."""

BOOLEANOS: tuple[str, ...] = tuple(
    campo.name for campo in fields(Atributos) if campo.type in ("bool", bool)
)
"""Os atributos que se **alternam** -- derivados de `Atributos`, e não recopiados.

É o que faz um booleano novo entrar em `alternar` sozinho, e é a mesma disciplina de
`texto_etiquetas._booleanos_de_atributo`, que cobra decisão de desenho para cada um deles."""


@dataclass(frozen=True)
class Corrida:
    """Um trecho contíguo de texto com os mesmos atributos -- a unidade do documento."""

    texto: str
    atributos: Atributos = PADRAO
    faixa: str = documento.TRANQUILO
    """A régua de confiança, de `text/documento.py`. **Não é atributo**: ver o cabeçalho."""

    bloco: int = SEM_BLOCO
    """Índice em `PaginaLida.blocos`, ou `SEM_BLOCO` para texto escrito à mão."""

    procedencia: Procedencia | None = None
    """Quem leu isto, ou `None` quando não veio de leitura nenhuma. Ver o cabeçalho."""

    tipo: str = TEXTO

    def __post_init__(self) -> None:
        if self.tipo not in TIPOS:
            raise KeyError(f"tipo de corrida desconhecido: {self.tipo!r}. Os válidos estão em TIPOS.")
        if self.procedencia is not None and self.procedencia not in PROCEDENCIAS:
            raise KeyError(f"procedência desconhecida: {self.procedencia!r}. As válidas estão em PROCEDENCIAS.")
        if self.faixa not in documento.FAIXAS:
            raise KeyError(f"faixa desconhecida: {self.faixa!r}. As válidas estão em documento.FAIXAS.")

    @property
    def e_diagrama(self) -> bool:
        return self.tipo == DIAGRAMA

    @property
    def da_pagina(self) -> bool:
        """Saiu de um bloco da página -- e não da mão de quem edita."""
        return self.bloco != SEM_BLOCO

    def _chave_de_fusao(self) -> tuple[Any, ...]:
        """Tudo o que **não** é o texto. Duas corridas com a mesma chave são a mesma corrida partida."""
        return (self.atributos, self.faixa, self.bloco, self.procedencia, self.tipo)

    def para_json(self) -> dict[str, Any]:
        dados: dict[str, Any] = {"texto": self.texto}
        # Os quatro campos de contexto só aparecem quando dizem alguma coisa, pela mesma razão de
        # `Atributos.para_json`: um documento de prosa comum não carrega quatro chaves por trecho.
        if not self.atributos.padrao:
            dados["atributos"] = self.atributos.para_json()
        if self.faixa != documento.TRANQUILO:
            dados["faixa"] = self.faixa
        if self.bloco != SEM_BLOCO:
            dados["bloco"] = self.bloco
        if self.procedencia is not None:
            dados["procedencia"] = self.procedencia
        if self.tipo != TEXTO:
            dados["tipo"] = self.tipo
        return dados

    @classmethod
    def de_json(cls, dados: Any) -> Corrida:
        if not isinstance(dados, dict):
            raise ValueError(f"corrida: esperava objeto, veio {type(dados).__name__}")
        return cls(
            texto=str(dados.get("texto", "")),
            atributos=Atributos.de_json(dados.get("atributos")),
            faixa=str(dados.get("faixa", documento.TRANQUILO)),
            bloco=int(dados.get("bloco", SEM_BLOCO)),
            procedencia=dados.get("procedencia"),
            tipo=str(dados.get("tipo", TEXTO)),
        )


def fundir(corridas: Iterable[Corrida]) -> tuple[Corrida, ...]:
    """Junta corridas vizinhas que só diferem no texto, e descarta as vazias.

    **Sem isto, digitar é o que estraga o documento.** Cada tecla numa implementação ingênua produz
    uma corrida de um caractere, e uma página corrigida à mão viraria mil corridas com os mesmos
    cinco atributos repetidos mil vezes -- no arquivo, na exportação e em toda travessia.

    Idempotente por construção: fundir o que já está fundido não acha vizinhas com a mesma chave.
    """
    saida: list[Corrida] = []
    for corrida in corridas:
        if not corrida.texto:
            # Corrida vazia não é conteúdo, e mantê-la faria a contagem de corridas depender de
            # quantas vezes alguém apagou uma seleção.
            continue
        if saida and saida[-1]._chave_de_fusao() == corrida._chave_de_fusao():
            anterior = saida[-1]
            saida[-1] = Corrida(
                texto=anterior.texto + corrida.texto,
                atributos=anterior.atributos,
                faixa=anterior.faixa,
                bloco=anterior.bloco,
                procedencia=anterior.procedencia,
                tipo=anterior.tipo,
            )
            continue
        saida.append(corrida)
    return tuple(saida)


@dataclass(frozen=True)
class DocumentoRico:
    """O que o editor mostra e o que o arquivo guarda -- a `PaginaLida` mais o que a mão fez nela."""

    corridas: tuple[Corrida, ...] = ()
    origem: PaginaLida | None = None
    """A página que originou isto, inteira. `None` para um documento escrito do zero.

    Vai junto porque é o que permite reabrir o arquivo e ainda ter bbox, confiança e diagrama --
    isto é, **recortar a miniatura de novo a partir do PDF** em vez de embutir imagem no arquivo.
    Ela já serializa sem perda por critério de aceite da S-211."""

    def para_texto(self) -> str:
        """O texto corrido, sem atributo nenhum.

        **Esta é a trava de não-regressão do item:** enquanto ela devolver o mesmo que
        `"".join(s.texto for s in documento.segmentos(pagina))`, trocar a fonte do `.txt` não muda o
        `.txt` de ninguém."""
        return "".join(corrida.texto for corrida in self.corridas)

    @property
    def diagramas(self) -> tuple[Corrida, ...]:
        """As corridas de diagrama, na ordem em que aparecem no texto."""
        return tuple(c for c in self.corridas if c.e_diagrama)

    def bloco_de(self, corrida: Corrida) -> Any:
        """O bloco da `PaginaLida` de onde a corrida saiu, ou `None` se ela não veio da página."""
        if self.origem is None or not corrida.da_pagina:
            return None
        blocos = self.origem.blocos
        return blocos[corrida.bloco] if 0 <= corrida.bloco < len(blocos) else None

    def normalizado(self) -> DocumentoRico:
        """O mesmo documento com as corridas fundidas. Ver `fundir`."""
        return DocumentoRico(corridas=fundir(self.corridas), origem=self.origem)

    def para_json(self) -> dict[str, Any]:
        """O documento como JSON. **Sem número de versão**, que é do formato de arquivo (S-238).

        Misturar os dois faria este módulo ter opinião sobre compatibilidade de arquivo, que é
        assunto de quem grava o arquivo -- e são duas coisas que envelhecem em ritmos diferentes."""
        dados: dict[str, Any] = {"corridas": [c.para_json() for c in self.corridas]}
        if self.origem is not None:
            dados["origem"] = self.origem.para_json()
        return dados

    @classmethod
    def de_json(cls, dados: Any) -> DocumentoRico:
        if not isinstance(dados, dict):
            raise ValueError(f"documento: esperava objeto, veio {type(dados).__name__}")
        origem = dados.get("origem")
        return cls(
            corridas=tuple(Corrida.de_json(c) for c in dados.get("corridas", ())),
            origem=PaginaLida.de_json(origem) if origem is not None else None,
        )


def de_pagina(pagina: PaginaLida) -> DocumentoRico:
    """A página lida como documento do editor. **A única ponte entre os dois.**

    O editor deixa de percorrer `documento.segmentos` direto e passa a desenhar isto, e a fronteira
    continua onde estava: `documento.py` é quem decide faixa, separador e ordem de leitura; este
    módulo não redecide nada disso -- traduz.

    O índice do bloco sai por **identidade** e não por igualdade: dois parágrafos com o mesmo texto,
    a mesma bbox e a mesma confiança são dataclasses congeladas iguais, e casá-los por `==` daria o
    mesmo índice aos dois -- que é a correção do primeiro indo para o bloco errado.
    """
    indice_de = {id(bloco): i for i, bloco in enumerate(pagina.blocos)}
    corridas: list[Corrida] = []
    for segmento in documento.segmentos(pagina):
        bloco = segmento.bloco
        corridas.extend(
            _corridas_do_segmento(
                segmento,
                bloco=indice_de.get(id(bloco), SEM_BLOCO) if bloco is not None else SEM_BLOCO,
                procedencia=getattr(bloco, "procedencia", None) if bloco is not None else None,
            )
        )
    return DocumentoRico(corridas=tuple(corridas), origem=pagina)


def _corridas_do_segmento(segmento: documento.Segmento, *, bloco: int, procedencia) -> list[Corrida]:  # noqa: ANN001
    """O segmento partido nas corridas que o desenham -- uma por trecho de mesma tipografia.

    **Por que um bloco vira mais de uma corrida.** O atributo do bloco é "todas as linhas ou
    `None`", e essa regra conservadora custa tudo na página real: medida a folha 311 do `Secrets of
    Chess Training`, ela tem **19 linhas em itálico** -- uma citação de 17 linhas seguidas -- e
    **nenhum bloco itálico**, porque a citação e a prosa em volta caíram no mesmo parágrafo de 38
    linhas. Desenhar por bloco ali seria desenhar nada.

    A `LinhaLida` sabe o que o bloco não sabe, e este é o lugar de usar: linhas vizinhas de mesma
    tipografia viram uma corrida.

    **E o texto não muda um caractere.** O corte é feito exatamente nos pontos em que `bloco.texto`
    junta as linhas, e o espaço da junção fica no fim da corrida anterior. Se a soma não bater com o
    que o bloco diz -- outro tipo de bloco, outra regra de junção --, sai uma corrida só: o texto
    vale mais que o atributo, e é ele que a S-235 travou.
    """
    tipo = _tipo_do_segmento(segmento)
    estilo = estilo_do_segmento(segmento)
    comum = {"faixa": segmento.faixa, "bloco": bloco, "procedencia": procedencia, "tipo": tipo}
    inteiro = Corrida(
        texto=segmento.texto,
        atributos=Atributos(negrito=segmento.negrito, italico=segmento.italico, estilo=estilo),
        **comum,
    )
    linhas = getattr(segmento.bloco, "linhas", ())
    if tipo != TEXTO or len(linhas) < 2:
        return [inteiro]
    if " ".join(linha.texto for linha in linhas) != segmento.texto:
        return [inteiro]

    grupos = _agrupar(linhas)
    saida: list[Corrida] = []
    for k, ((negrito, italico), textos) in enumerate(grupos):
        junta = " ".join(textos)
        # O espaço da junção fica no fim da corrida anterior, e não no começo da seguinte: assim a
        # corrida itálica começa na primeira letra da citação, e não num espaço em pé antes dela.
        saida.append(
            Corrida(
                texto=junta if k == len(grupos) - 1 else junta + " ",
                atributos=Atributos(negrito=negrito, italico=italico, estilo=estilo),
                **comum,
            )
        )
    return saida


def estilo_do_segmento(segmento: documento.Segmento) -> str:
    """O estilo de parágrafo que a **página** declara para aquele bloco (S-249).

    Dois dos quatro saem da página lida, e os dois têm dono no modelo da S-211:

        BlocoDeTarja              -> título    texto claro sobre fundo escuro é cabeçalho (S-195)
        BlocoDeTexto com recuado  -> prosa     o recuo que a S-199 mede para separar parágrafo

    **`legenda` entrou em 2026-08-25**, e ela não é decidida aqui: é lida de `BlocoDeTexto.legenda_de`,
    que o leitor grava a partir de `pdf_text.assign_lines_to_diagrams` -- o dono daquela pergunta
    desde a S-16, com a régua medida. O que este módulo acrescenta é **uma guarda de conteúdo**, e
    ela tem número: dos 83 parágrafos que aquela régua ata a um diagrama no conjunto de campo,
    **14 (17%) são linha de lances**, não legenda. A régua mede distância, não conteúdo -- e pintar
    uma variante com o corpo de legenda seria um erro visível. Quem separa é
    `notacao.e_linha_de_notacao`, que é a régua de lance que este subpacote já tinha.

    Com a guarda, **69 dos 112 diagramas do conjunto de campo (61,6%) ganham legenda desenhada**;
    sem ela seriam 83 (74,1%), com catorze variantes pintadas de legenda.

    **`notacao` continua entrando só pela mão, e agora com número.** Medido em 2026-08-26 sobre
    305 blocos rotulados à mão (`docs/metrics/texto_notacao_estilo.json`), a régua acerta 89% do
    que estilaria e alcança 75% das linhas de lances -- e os 11% que ela erraria são título
    corrente e número de página, que virariam notação na cara do leitor. Não é o bastante para
    pintar sozinha, e a regra 5 da SPEC_EDITOR manda entregar o pincel em vez de pintar palpite.

    A guarda acima não é a mesma pergunta: ela decide sobre um parágrafo que já se sabe atado a um
    diagrama -- população muito menor, e muito mais fácil --, e ali um erro tira um estilo em vez
    de pôr um errado.
    """
    bloco = segmento.bloco
    if bloco is None or segmento.tipo != TEXTO:
        return ""
    tipo = getattr(bloco, "tipo", "")
    if tipo == "tarja":
        return ESTILO_TITULO
    if tipo != "texto":
        return ""
    if getattr(bloco, "legenda_de", None) is not None and not notacao.e_linha_de_notacao(segmento.texto):
        # A legenda ganha do recuo: um parágrafo pode ser as duas coisas, e o que ele **é** para
        # quem lê a página é a legenda do diagrama ao lado.
        return ESTILO_LEGENDA
    if getattr(bloco, "recuado", False):
        return ESTILO_PROSA
    return ""


def _agrupar(linhas: Sequence[Any]) -> list[tuple[tuple[bool, bool], list[str]]]:
    """Linhas vizinhas de mesma tipografia, na ordem. `None` conta como "não", como na tela."""
    grupos: list[tuple[tuple[bool, bool], list[str]]] = []
    for linha in linhas:
        chave = (getattr(linha, "negrito", None) is True, getattr(linha, "italico", None) is True)
        if grupos and grupos[-1][0] == chave:
            grupos[-1][1].append(linha.texto)
            continue
        grupos.append((chave, [linha.texto]))
    return grupos


def _tipo_do_segmento(segmento: documento.Segmento) -> str:
    """O tipo da corrida a partir do tipo do segmento, recusando o que não conhecemos.

    `documento.Segmento.tipo` é `str` livre; `Corrida.tipo` é fechado. A conversão é onde essa
    diferença aparece, e deixá-la implícita faria um segmento de tipo novo virar corrida de texto em
    silêncio -- e o editor desenharia uma tabela como se fosse parágrafo.
    """
    if segmento.tipo not in TIPOS:
        raise KeyError(f"segmento de tipo desconhecido: {segmento.tipo!r}. Os válidos estão em TIPOS.")
    return segmento.tipo


def corridas_de_texto(texto: str, *, atributos: Atributos = PADRAO) -> tuple[Corrida, ...]:
    """Um documento escrito do zero: uma corrida, sem bloco e sem procedência.

    Existe para o caminho que a S-238 vai precisar -- abrir um arquivo cujo PDF sumiu -- e para os
    testes não montarem uma `PaginaLida` inteira só para afirmar uma fusão.
    """
    return fundir([Corrida(texto=texto, atributos=atributos)])


def de_texto(texto: str) -> DocumentoRico:
    """Um documento sem página: só o que alguém escreveu."""
    return DocumentoRico(corridas=corridas_de_texto(texto))


# ----------------------------------------------------------------- a edição (S-241, S-242, S-249)

LETRAS_DE_PALAVRA_EXTRA = "'-’"
"""Além de `str.isalnum()`, o que ainda é palavra: apóstrofo e hífen.

**O limite de palavra é declarado aqui e em nenhum outro lugar** (critério de aceite da S-241).
`Black's` é uma palavra e não três, e `em-barrassment` na quebra de linha é o caso que a S-209 já
trata do outro lado. Figurina (`♘`) **não** entra: ela é símbolo, e um `♘` colado num lance faria
"a palavra sob o cursor" engolir o lance inteiro."""


def _e_de_palavra(caractere: str) -> bool:
    return caractere.isalnum() or caractere in LETRAS_DE_PALAVRA_EXTRA


def palavra_em(texto: str, posicao: int) -> tuple[int, int]:
    """O começo e o fim da palavra sob aquela posição. Intervalo vazio quando não há palavra.

    Olha para trás **e** para a frente a partir do cursor. O cursor logo depois da última letra
    ainda está na palavra -- é onde ele fica quando alguém acaba de digitá-la, e é o momento em que
    se aperta `Ctrl+B`.
    """
    if not texto:
        return (0, 0)
    limite = max(0, min(int(posicao), len(texto)))
    inicio = limite
    while inicio > 0 and _e_de_palavra(texto[inicio - 1]):
        inicio -= 1
    fim = limite
    while fim < len(texto) and _e_de_palavra(texto[fim]):
        fim += 1
    return (inicio, fim)


def intervalo_alvo(doc: DocumentoRico, inicio: int, fim: int) -> tuple[int, int]:
    """O intervalo em que o comando vai agir: o selecionado, ou a palavra sob o cursor.

    **Sem seleção, o alvo é a palavra** -- é o comportamento que evita a pergunta *"por que não
    aconteceu nada?"*, e ele é decidido aqui, na função pura, e não no widget.
    """
    texto = doc.para_texto()
    inicio, fim = sorted((max(0, min(int(inicio), len(texto))), max(0, min(int(fim), len(texto)))))
    if inicio != fim:
        return (inicio, fim)
    return palavra_em(texto, inicio)


def intervalo_de_paragrafo(doc: DocumentoRico, inicio: int, fim: int) -> tuple[int, int]:
    """O intervalo em que um comando **de parágrafo** age. Não é `intervalo_alvo` (S-259).

    **O defeito que ele conserta, medido na tela.** `intervalo_alvo` cai na *palavra* sob o cursor
    quando não há seleção, e sobre um caractere que não é de palavra a palavra é **vazia** -- então
    o comando não faz nada. Para negrito isso é o certo: não há o que emboldecer num espaço. Para
    alinhamento e estilo é o contrário: o cursor sobre o `[` de `[Diagrama 1]` é exatamente onde
    alguém está quando quer centralizar a figura, e ali "não acontece nada" é a resposta errada.

    A regra: seleção manda; senão a palavra sob o cursor; senão o **caractere** sob o cursor, que
    basta -- quem estende ao bloco inteiro é `aplicar_no_paragrafo`. Num documento vazio devolve
    `(0, 0)`, e o comando não tem o que fazer mesmo.
    """
    texto = doc.para_texto()
    inicio, fim = sorted((max(0, min(int(inicio), len(texto))), max(0, min(int(fim), len(texto)))))
    if inicio != fim:
        return (inicio, fim)
    palavra = palavra_em(texto, inicio)
    if palavra[0] != palavra[1]:
        return palavra
    if inicio < len(texto):
        return (inicio, inicio + 1)
    return (max(0, inicio - 1), inicio)


def _fatiado(doc: DocumentoRico, inicio: int, fim: int) -> list[tuple[Corrida, bool]]:
    """As corridas partidas nos dois limites, cada uma com "está dentro do intervalo?".

    Partir aqui é o que permite todo o resto ser um `replace` por corrida: quem aplica não precisa
    saber que o intervalo pode cair no meio de uma corrida, e a fusão de `fundir` desfaz depois os
    cortes que não separaram nada.
    """
    saida: list[tuple[Corrida, bool]] = []
    posicao = 0
    for corrida in doc.corridas:
        comeco, termino = posicao, posicao + len(corrida.texto)
        posicao = termino
        cortes = sorted({comeco, termino, *(c for c in (inicio, fim) if comeco < c < termino)})
        # `strict=False`: `cortes[1:]` tem sempre um elemento a menos -- isto e um `pairwise`,
        # e nao duas listas que deveriam andar juntas.
        for a, b in zip(cortes, cortes[1:], strict=False):
            pedaco = corrida.texto[a - comeco : b - comeco]
            if pedaco:
                saida.append((replace(corrida, texto=pedaco), inicio <= a and b <= fim))
    return saida


def _editavel(corrida: Corrida) -> bool:
    """Só corrida de texto recebe atributo.

    A marca do diagrama e o separador não são texto do livro: o widget os devolve com `PADRAO` por
    construção (`texto_etiquetas.corrida_de`), e pintar de negrito um `[Diagrama 3]` seria um
    atributo que morre na primeira gravação -- o defeito que a S-235 existe para impedir.
    """
    return corrida.tipo == TEXTO


ATRIBUTOS_DA_MARCA: frozenset[str] = frozenset({"alinhamento"})
"""O que a marca do diagrama aceita, e é **um só** (S-259).

`_editavel` recusa atributo em `[Diagrama N]` porque atributo de marca morre na gravação -- e essa
regra continua valendo para os outros nove. O alinhamento é a exceção porque ele não descreve a
marca: descreve **onde a figura fica na coluna**, que é uma pergunta que a página faz e o editor
precisa responder. Sem ele, "centralizar a figura" teria de virar um segundo mecanismo ao lado do
alinhamento do texto -- dois caminhos para a mesma escolha, que é a divergência que `ui/comandos.py`
existe para impedir noutro lugar.

O outro lado desta exceção mora em `ui/texto_etiquetas.py`: a marca **emite e devolve** a etiqueta
de alinhamento, e nada mais. Os dois têm de concordar, e o teste de ida e volta é quem os compara.
"""


def _recebe(corrida: Corrida, valores: Iterable[str]) -> bool:
    """Aquela corrida aceita **estes** atributos? É `_editavel` com a exceção da marca.

    Separado de `_editavel` porque a pergunta passou a depender do que se está escrevendo: negrito
    numa marca continua recusado, alinhamento não. Um `_editavel` que dissesse `True` para a marca
    abriria os dez.
    """
    if _editavel(corrida):
        return True
    if corrida.tipo == DIAGRAMA:
        return bool(valores) and set(valores) <= ATRIBUTOS_DA_MARCA
    return False


def vale_em_todo(doc: DocumentoRico, inicio: int, fim: int, atributo: str) -> bool:
    """O atributo vale em **todo** o intervalo? É a pergunta que decide ligar ou desligar.

    "Vale no primeiro caractere?" daria o comportamento errado no caso mais comum: selecionar uma
    frase cuja primeira palavra já está em negrito e apertar `Ctrl+B` tem de **completar** o
    negrito, e não apagá-lo.

    Intervalo sem corrida de texto nenhuma responde `False`: não há o que desligar.
    """
    dentro = [c for c, esta in _fatiado(doc, inicio, fim) if esta and _editavel(c)]
    if not dentro:
        return False
    return all(bool(getattr(c.atributos, atributo)) for c in dentro)


def valor_em_todo(doc: DocumentoRico, inicio: int, fim: int, atributo: str) -> Any | None:
    """O valor deste atributo, se ele for **o mesmo** em todo o intervalo. `None` se divergir.

    É o irmão de `vale_em_todo` para atributo que não é sim-ou-não (S-292), e existe pela mesma
    razão que aquele: a barra tem de dizer o que vale sob o cursor, e quem responde tem de ser a
    **mesma** função que decide -- duas respostas para a mesma pergunta divergem, e a que fica
    errada é a da tela, porque ninguém a testa.

    **`None` e `""` são respostas diferentes, e a distinção é o item.** `""` é "todo o intervalo
    está sem alinhamento"; `None` é "há mais de um alinhamento aqui" -- e é o que faz a lista da
    barra não marcar nenhum item em vez de marcar um que vale só em metade da seleção.

    Intervalo sem corrida de texto nenhuma responde `None`: não há valor a mostrar.
    """
    dentro = [c for c, esta in _fatiado(doc, inicio, fim) if esta and _editavel(c)]
    if not dentro:
        return None
    valores = {getattr(c.atributos, atributo) for c in dentro}
    return valores.pop() if len(valores) == 1 else None


def aplicar(doc: DocumentoRico, inicio: int, fim: int, **valores: Any) -> DocumentoRico:
    """Escreve estes atributos nas corridas de texto do intervalo, e carimba `humano`.

    **O carimbo é o item da S-239 aplicado a atributo.** Desmarcar à mão um itálico que a régua da
    S-236 detectou é uma correção sobre o que o motor leu -- e é exatamente o tipo de informação
    que a fila da S-212 quer. Sem ele, a marcação humana só apareceria quando o *texto* mudasse.
    """
    if not valores:
        return doc
    for nome in valores:
        if nome not in {campo.name for campo in fields(Atributos)}:
            raise KeyError(f"atributo desconhecido: {nome!r}. Os válidos estão em `Atributos`.")
    novas = [
        replace(corrida, atributos=replace(corrida.atributos, **valores), procedencia="humano")
        if esta and _editavel(corrida)
        else corrida
        for corrida, esta in _fatiado(doc, inicio, fim)
    ]
    return DocumentoRico(corridas=fundir(novas), origem=doc.origem)


def alternar(doc: DocumentoRico, inicio: int, fim: int, atributo: str) -> DocumentoRico:
    """Liga o atributo no intervalo -- ou desliga, se ele já vale em todo ele (S-241).

    Sem seleção (`inicio == fim`), o alvo é a palavra sob o cursor: ver `intervalo_alvo`.
    """
    if atributo not in BOOLEANOS:
        raise KeyError(f"atributo alternável desconhecido: {atributo!r}. Os válidos estão em BOOLEANOS.")
    inicio, fim = intervalo_alvo(doc, inicio, fim)
    if inicio == fim:
        return doc
    return aplicar(doc, inicio, fim, **{atributo: not vale_em_todo(doc, inicio, fim, atributo)})


def limpar_formato(doc: DocumentoRico, inicio: int, fim: int) -> DocumentoRico:
    """Tira negrito, itálico e sublinhado do intervalo. **Não** toca em cor nem em estilo.

    A cor tem comando próprio (`limpar_cor`, S-242) porque ela é de outro canal e de outra decisão:
    quem quer tirar a ênfase tipográfica de um trecho quase nunca quer também apagar a marcação
    colorida que fez para si.
    """
    inicio, fim = intervalo_alvo(doc, inicio, fim)
    if inicio == fim:
        return doc
    return aplicar(doc, inicio, fim, negrito=False, italico=False, sublinhado=False)


def limpar_cor(doc: DocumentoRico, inicio: int, fim: int) -> DocumentoRico:
    """Tira a cor do autor -- letra e realce -- e **não** toca na faixa de confiança (S-242).

    A faixa não é atributo: ela mora em `Corrida.faixa`, que este caminho não escreve. É a mesma
    fronteira do cabeçalho deste módulo, e é o que faz "limpar cor" não apagar a informação de que
    o motor estava adivinhando ali.
    """
    inicio, fim = intervalo_alvo(doc, inicio, fim)
    if inicio == fim:
        return doc
    return aplicar(doc, inicio, fim, cor="", realce="")


def aplicar_no_paragrafo(doc: DocumentoRico, inicio: int, fim: int, **valores: Any) -> DocumentoRico:
    """Escreve estes atributos no **parágrafo inteiro** que o intervalo toca (S-249/S-259).

    Estilo e alinhamento são do parágrafo, e o documento não tem parágrafo: tem corridas. O
    parágrafo é o conjunto de corridas do mesmo bloco -- que é como a página chegou --, então marcar
    meia frase marcaria meio parágrafo, e o desenho ficaria com dois corpos de fonte na mesma linha.

    Texto escrito do zero (`SEM_BLOCO`) não tem bloco a que se estender: ali o alvo são as corridas
    tocadas, inteiras.

    **A marca do diagrama entra quando -- e só quando -- o atributo é dela** (`ATRIBUTOS_DA_MARCA`).
    É o que faz centralizar um parágrafo que contém uma figura centralizar a figura junto, sem abrir
    a marca para os outros atributos.

    O alvo sai de `intervalo_de_paragrafo`, e **não** de `intervalo_alvo`: o cursor parado no `[` de
    `[Diagrama 1]` é onde alguém está quando quer centralizar a figura, e ali não há palavra.
    """
    inicio, fim = intervalo_de_paragrafo(doc, inicio, fim)
    if inicio == fim:
        return doc
    blocos = {
        c.bloco for c, esta in _fatiado(doc, inicio, fim) if esta and _recebe(c, valores) and c.da_pagina
    }
    novas: list[Corrida] = []
    posicao = 0
    for corrida in doc.corridas:
        comeco, termino = posicao, posicao + len(corrida.texto)
        posicao = termino
        tocada = comeco < fim and termino > inicio
        if _recebe(corrida, valores) and (corrida.bloco in blocos or tocada):
            novas.append(
                replace(
                    corrida,
                    atributos=replace(corrida.atributos, **valores),
                    procedencia="humano",
                )
            )
            continue
        novas.append(corrida)
    return DocumentoRico(corridas=fundir(novas), origem=doc.origem)


def aplicar_estilo(doc: DocumentoRico, inicio: int, fim: int, estilo: str) -> DocumentoRico:
    """O estilo de parágrafo do intervalo (S-249). Ver `aplicar_no_paragrafo` sobre o alcance."""
    if estilo and estilo not in ESTILOS:
        raise KeyError(f"estilo desconhecido: {estilo!r}. Os válidos estão em ESTILOS.")
    return aplicar_no_paragrafo(doc, inicio, fim, estilo=estilo)


def aplicar_alinhamento(doc: DocumentoRico, inicio: int, fim: int, alinhamento: str) -> DocumentoRico:
    """O alinhamento do parágrafo do intervalo -- **e o da figura dentro dele** (S-259)."""
    if alinhamento and alinhamento not in ALINHAMENTOS:
        raise KeyError(f"alinhamento desconhecido: {alinhamento!r}. Os válidos estão em ALINHAMENTOS.")
    return aplicar_no_paragrafo(doc, inicio, fim, alinhamento=alinhamento)


def aplicar_corpo(doc: DocumentoRico, inicio: int, fim: int, degrau: int) -> DocumentoRico:
    """Põe **este** degrau de corpo no intervalo. É o "voltar ao normal", com `degrau=0` (S-260)."""
    inicio, fim = intervalo_alvo(doc, inicio, fim)
    if inicio == fim:
        return doc
    return aplicar(doc, inicio, fim, corpo=corpo_no_limite(degrau))


def mudar_corpo(doc: DocumentoRico, inicio: int, fim: int, passo: int) -> DocumentoRico:
    """Soma `passo` ao corpo de **cada** corrida do intervalo, grampeado na faixa (S-260).

    Soma por corrida, e não um valor só para todas: selecionar um título (`+2`) junto de duas linhas
    de prosa (`0`) e apertar "aumentar" tem de subir os três um degrau, e não achatar os três no
    mesmo número. É a mesma pergunta que `vale_em_todo` responde para o negrito -- o comando age
    sobre o que está lá, e não sobre um estado que ele supõe.

    Corrida que já está no limite fica onde está, e as outras andam: parar o gesto inteiro porque uma
    palavra chegou ao teto seria o botão que "não faz nada" sem dizer por quê.
    """
    inicio, fim = intervalo_alvo(doc, inicio, fim)
    if inicio == fim or not passo:
        return doc
    novas = [
        replace(
            corrida,
            atributos=replace(
                corrida.atributos, corpo=corpo_no_limite(corrida.atributos.corpo + int(passo))
            ),
            procedencia="humano",
        )
        if esta and _editavel(corrida)
        else corrida
        for corrida, esta in _fatiado(doc, inicio, fim)
    ]
    return DocumentoRico(corridas=fundir(novas), origem=doc.origem)


NAO_ABREM_PALAVRA = "'’"
"""Os apóstrofos: eles ficam **dentro** da palavra quando se capitaliza (S-262).

**É `LETRAS_DE_PALAVRA_EXTRA` menos o hífen, e a diferença é medida no acervo.** Para achar o alvo de
um comando (`palavra_em`), `saint-amant` é uma palavra só -- o duplo clique de qualquer editor a
seleciona inteira. Para capitalizar, ela é **duas**: o jogador se chama Saint-Amant, e um
`Saint-amant` num índice de nomes é um erro que ninguém revisa depois.

O apóstrofo é o contrário nos dois: `don't` capitalizado é `Don't`, e não `Don'T` -- que é
exatamente o que `str.title()` devolve, e a razão de esta função existir em vez daquela."""


def _capitular(texto: str) -> str:
    """Iniciais maiúsculas -- o Title Case que o Word faz, e não o de `str.title()` (S-262).

    Duas regras, e as duas são critério de aceite: o apóstrofo **não** abre palavra (`don't` ->
    `Don't`), e o hífen **abre** (`saint-amant` -> `Saint-Amant`). Ver `NAO_ABREM_PALAVRA` sobre
    por que este corte não é o mesmo de `palavra_em`.
    """
    saida: list[str] = []
    comecando = True
    for caractere in texto:
        if not (caractere.isalnum() or caractere in NAO_ABREM_PALAVRA):
            comecando = True
            saida.append(caractere)
            continue
        saida.append(caractere.upper() if comecando else caractere.lower())
        comecando = False
    return "".join(saida)


_TROCAS_DE_CAIXA = {
    CAIXA_ALTA: str.upper,
    CAIXA_BAIXA: str.lower,
    CAIXA_INICIAIS: _capitular,
}


def mudar_caixa(doc: DocumentoRico, inicio: int, fim: int, caixa: str) -> DocumentoRico:
    """Troca a caixa do texto do intervalo, **corrida a corrida** (S-262).

    Corrida a corrida, e não sobre o texto junto, porque cada uma carrega atributo, faixa e bloco
    próprios: passar o intervalo por `substituir_intervalo` daria o texto certo com a formatação da
    primeira corrida em todas -- um negrito que engole o parágrafo.

    A marca do diagrama e o separador atravessam inteiros. `[Diagrama 3]` em maiúscula deixaria de
    ser a marca que `text/documento.py` escreve, e o que se perderia não é a caixa: é o vínculo entre
    o texto e a figura.
    """
    if caixa not in _TROCAS_DE_CAIXA:
        raise KeyError(f"caixa desconhecida: {caixa!r}. As válidas estão em CAIXAS.")
    inicio, fim = intervalo_alvo(doc, inicio, fim)
    if inicio == fim:
        return doc
    troca = _TROCAS_DE_CAIXA[caixa]
    novas: list[Corrida] = []
    for corrida, esta in _fatiado(doc, inicio, fim):
        if not esta or not _editavel(corrida):
            novas.append(corrida)
            continue
        trocado = troca(corrida.texto)
        novas.append(
            corrida if trocado == corrida.texto else replace(corrida, texto=trocado, procedencia="humano")
        )
    return DocumentoRico(corridas=fundir(novas), origem=doc.origem)


def substituir_intervalo(doc: DocumentoRico, inicio: int, fim: int, novo: str) -> DocumentoRico:
    """Troca o texto do intervalo por outro, **mantendo os atributos** de quem estava ali (S-245).

    "Trocar uma palavra em negrito devolve a palavra nova em negrito" é critério de aceite da busca,
    e é aqui que ele mora: o texto novo herda os atributos, a faixa e o bloco da primeira corrida do
    intervalo. O bloco é o que faz a troca continuar sendo uma **correção sobre aquele bloco** --
    sem ele, `text/correcao.py` deixaria de ver o que a substituição em massa fez.
    """
    inicio, fim = sorted((max(0, inicio), max(0, fim)))
    if inicio == fim:
        return inserir(doc, inicio, novo)
    partido = _fatiado(doc, inicio, fim)
    novas: list[Corrida] = []
    posto = False
    for corrida, esta in partido:
        if not esta or not _editavel(corrida):
            # Marca de diagrama e separador atravessam a troca inteiros: apagá-los seria a busca
            # editando a estrutura do texto, e não o texto (a regra do cabeçalho de `documento.py`).
            novas.append(corrida)
            continue
        if not posto and novo:
            novas.append(replace(corrida, texto=novo, procedencia="humano"))
            posto = True
    return DocumentoRico(corridas=fundir(novas), origem=doc.origem)


def inserir(doc: DocumentoRico, posicao: int, texto: str, *, fora_do_modelo: bool = False) -> DocumentoRico:
    """Insere texto na posição, herdando os atributos de quem está à esquerda (S-248).

    **Herda da esquerda, e não do padrão**, pela mesma regra que o Tk já usa para a digitação: quem
    põe uma figurina no meio de um lance em negrito quer a figurina em negrito. `fora_do_modelo`
    entra por cima, porque é declaração sobre o que foi inserido e não sobre o que estava lá.
    """
    if not texto:
        return doc
    posicao = max(0, min(int(posicao), len(doc.para_texto())))
    esquerda = None
    caminhado = 0
    for corrida in doc.corridas:
        caminhado += len(corrida.texto)
        if _editavel(corrida) and caminhado >= posicao > caminhado - len(corrida.texto):
            esquerda = corrida
            break
    atributos = esquerda.atributos if esquerda is not None else PADRAO
    if fora_do_modelo:
        atributos = replace(atributos, fora_do_modelo=True)
    nova = Corrida(
        texto=texto,
        atributos=atributos,
        faixa=esquerda.faixa if esquerda is not None else documento.TRANQUILO,
        bloco=esquerda.bloco if esquerda is not None else SEM_BLOCO,
        procedencia="humano",
    )
    partido = _fatiado(doc, posicao, posicao)
    novas: list[Corrida] = []
    caminhado = 0
    inseriu = False
    for corrida, _esta in partido:
        if not inseriu and caminhado == posicao:
            novas.append(nova)
            inseriu = True
        novas.append(corrida)
        caminhado += len(corrida.texto)
    if not inseriu:
        novas.append(nova)
    return DocumentoRico(corridas=fundir(novas), origem=doc.origem)


__all__ = [
    "BOOLEANOS",
    "CORES_DE_AUTOR",
    "DIAGRAMA",
    "ESTILOS",
    "ESTILO_LEGENDA",
    "ESTILO_NOTACAO",
    "ESTILO_PROSA",
    "ESTILO_TITULO",
    "LETRAS_DE_PALAVRA_EXTRA",
    "NAO_ABREM_PALAVRA",
    "PADRAO",
    "PROCEDENCIAS",
    "SEM_BLOCO",
    "SEPARADOR",
    "TEXTO",
    "TIPOS",
    "Atributos",
    "Corrida",
    "DocumentoRico",
    "ALINHAMENTOS",
    "ALINHAMENTO_CENTRO",
    "ALINHAMENTO_DIREITA",
    "ALINHAMENTO_ESQUERDA",
    "ALINHAMENTO_JUSTIFICADO",
    "ATRIBUTOS_DA_MARCA",
    "CAIXAS",
    "CAIXA_ALTA",
    "CAIXA_BAIXA",
    "CAIXA_INICIAIS",
    "CORPO_MAXIMO",
    "CORPO_MINIMO",
    "alternar",
    "aplicar",
    "aplicar_alinhamento",
    "aplicar_corpo",
    "aplicar_estilo",
    "aplicar_no_paragrafo",
    "corpo_no_limite",
    "corridas_de_texto",
    "de_pagina",
    "de_texto",
    "estilo_do_segmento",
    "fundir",
    "inserir",
    "intervalo_alvo",
    "intervalo_de_paragrafo",
    "substituir_intervalo",
    "limpar_cor",
    "limpar_formato",
    "mudar_caixa",
    "mudar_corpo",
    "palavra_em",
    "vale_em_todo",
    "valor_em_todo",
]
