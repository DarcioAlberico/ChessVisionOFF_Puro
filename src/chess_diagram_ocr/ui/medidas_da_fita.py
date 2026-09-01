"""O que a fita **é** e quanta altura ela custa, sem toolkit nenhum (S-227/S-228/S-503).

Os dois modos, o lado do ícone em cada um, o orçamento em pixel, a quebra do rótulo, a histerese,
os grupos como dado e a conta da altura. É a fita inteira menos os widgets -- e o cabeçalho de
`ui/fita.py` já dizia por que ela era assim: *"`altura_da_fita`, que é **pura**: a altura se
afirma na suíte sem `winfo_height` no critério"*.

**Por que isso mudou de arquivo.** Faltava a consequência de ser puro. O `ui/fita.py` importa
`tkinter` na primeira linha do corpo, e tem de importar: `Fita` herda de `BarraFluida`, que herda
de `ttk.Frame`, e classe-base é avaliada na importação. Então o orçamento era afirmável sem
janela e, ainda assim, ninguém o lia sem carregar o Tk junto -- o mesmo defeito que a S-501
corrigiu em `ui/rodape.py` e em `ui/board_render.py`, pelo mesmo caminho.

**Aqui a cópia custaria mais que nos outros dois.** `grupos()` decide **quais** botões existem, e
`altura_da_fita` conta exatamente esses -- então uma segunda cópia não divergiria só na aparência:
a fita de uma janela teria um comando que a da outra não tem, e o orçamento de 120 px estaria sendo
medido sobre uma fita que não é a desenhada. O número continuaria verde e deixaria de significar
alguma coisa.

**O que ficou de fora, e a fronteira é essa.** `linhas_de_fonte` e `altura_atual` continuam em
`ui/fita.py`: as duas leem a fonte *do Tk* (`tkfont.Font(...).metrics("linespace")`), e são a
tradução de "a fonte deste sistema" para os dois parâmetros que a conta pede. Cada frontend tem a
sua -- `qt/fita.py` tem a dele --, e as duas chamam a **mesma** `altura_da_fita`, que é onde o
orçamento mora.

**As três medidas do botão são do `ttk.Button`, e continuam aqui de propósito.**
`MOLDURA_DO_BOTAO`, `FOLGA_ACIMA_DO_ROTULO` e `MOLDURA_DO_CABECALHO` saíram de medir aquele
widget, e um `QToolButton` tem o cromo dele. Movê-las para o lado do Tk faria cada frontend prever
uma altura diferente para a **mesma** decisão -- e o orçamento deixaria de ser um número do
programa para virar dois números de dois desenhos. O que o segundo frontend confere é o que o
primeiro confere: que a fita montada não passa do previsto. Ver `qt/fita.py`.

`ui/fita.py` reexportava tudo o que está aqui, e saiu no corte do Tk (S-506). Quem consome agora
é `qt/fita.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import comandos, pele, tipografia

__all__ = [
    "COMPACTO",
    "FOLGA_ACIMA_DO_ROTULO",
    "HISTERESE",
    "LADO_DO_ICONE",
    "LINHAS_DO_ROTULO",
    "MODOS",
    "MOLDURA_DO_BOTAO",
    "MOLDURA_DO_CABECALHO",
    "ORCAMENTO",
    "PLENO",
    "GrupoDeFita",
    "acoes_da_fita",
    "altura_da_fita",
    "espaco_ate_o_cabecalho",
    "espaco_entre_botoes",
    "grupos",
    "quebrar_rotulo",
]

PLENO = "pleno"
"""Ícone grande, rótulo embaixo, cabeçalho de grupo à vista. É a Imagem 2 desenhada."""

COMPACTO = "compacto"
"""Ícone pequeno, rótulo ao lado, cabeçalho na dica. É a mesma fita numa janela que não a comporta."""

MODOS: tuple[str, ...] = (PLENO, COMPACTO)

LADO_DO_ICONE: dict[str, int] = {PLENO: 32, COMPACTO: 20}
"""O lado do ícone em cada modo, em pixel.

No pleno ele fica **acima** do rótulo: sem uma palavra grudada nele, o ícone carrega o
reconhecimento sozinho, e 32 px é o tamanho em que o traço de `ui/icones.py` (9% do lado, ~3 px)
ainda se lê como desenho. No compacto ele volta a ser marca ao lado do texto, como a pílula da
pele "Foco" -- e 20 px é o que não faz o botão crescer além da linha de texto."""

ORCAMENTO: dict[str, int] = {PLENO: 120, COMPACTO: 64}
"""Quanta altura cada modo pode gastar, em pixel. **Declarado, e verificado na suíte.**

Os dois números não são gosto. **120 px é 12%** de uma janela de 1000 de altura -- abaixo dos 20%
que a S-151 chamou de defeito, e acima dos ~56 px das duas barras de hoje, que é o que a fita custa
a mais em troca de legibilidade. **64 px** é o que cabe sem a fita competir com a página num
1366×768, que é a tela em que a S-151 mediu o problema original."""

LINHAS_DO_ROTULO = 2
"""Em quantas linhas o rótulo do botão pode quebrar. **Duas nos dois modos**, e isso foi medido.

**Medido, e não escolhido.** Sem quebra, "Apagar a peça da casa selecionada" vira um botão de 230
px e a fita inteira pede mais de 2.000 -- ela nasceria em duas linhas em qualquer tela, o que
derrota a fita antes de o orçamento chegar.

> ## O achado da S-228: "rótulo ao lado" é **mais largo**, e não mais estreito
>
> A spec desenha o modo compacto com o rótulo ao lado do ícone, e a intuição é que uma linha só de
> texto ocupa menos. Ela ocupa menos **altura** e muito mais **largura**, e a fita paga em largura:
>
> | forma | largura de uma linha | linhas em 1366 | altura em 1366 |
> |---|---:|---:|---:|
> | pleno: ícone 32 em cima, 2 linhas, cabeçalho | 1.375 px | 2 | 200 px |
> | compacto com o rótulo em **uma** linha | 2.317 px | **3** | 106 px |
> | compacto com o rótulo em **duas** linhas | 1.726 px | 2 | **90 px** |
>
> Uma linha de rótulo transformaria o modo que existe para caber num modo que pede **três** linhas
> de fita na tela em que ele foi inventado para servir. O compacto herda a quebra do pleno, e o que
> o faz compacto são as outras três coisas: ícone menor, rótulo ao lado e cabeçalho na dica --
> 44 px de linha contra 99, que é o que o orçamento pede.
>
> **E o compacto é mais largo que o pleno mesmo assim** -- 1.726 contra 1.375, com a mesma quebra.
> Não é anomalia, é a forma: o rótulo sai de baixo do ícone e vai para o lado dele, e **o que era
> altura vira largura**. O modo compacto compra altura e paga em largura, e é por isso que reduzir
> o rótulo a uma linha -- que parece "compactar mais" -- é o que o destrói.

**E não se encurta o rótulo**: nenhum item desta fase troca o texto de comando nenhum (achado 1 do
roadmap). As mesmas palavras, noutra quebra."""

HISTERESE = 24
"""Quantos pixels a mais a janela precisa ter para a fita **voltar** ao modo pleno.

Sem ela a troca é reversível no mesmo pixel: uma janela arrastada até a vizinhança do limiar troca
de modo a cada pixel de tremor, e cada troca **destrói e recria os dezessete botões**. Vinte e
quatro pixels é mais que o tremor de um arrasto e menos que um botão -- separa os dois sentidos sem
chegar a exigir arrastar a janela duas vezes para desfazer o que ela acabou de fazer.

**O que ela não é.** A primeira redação deste docstring justificava a histerese por um laço --
"o compacto pede menos largura, o recipiente encolhe até a largura pedida, e a largura pedida volta
a autorizar o pleno". **A premissa é falsa, e foi medida:** o compacto pede *mais* largura que o
pleno (1.726 px contra 1.375), porque o rótulo sai de baixo do ícone e vai para o lado dele -- o que
era altura vira largura. O laço descrito não existe, e a razão de a histerese ficar é a de cima,
que é outra."""

# ------------------------------------------------------------------- as medidas do ttk.Button
#
# **Medidas, e não estimativas.** Os três números abaixo saíram de montar o botão e ler
# `winfo_reqheight` nos três tamanhos de ícone (20, 24 e 32) e nas duas contagens de linha, com o
# tema padrão do programa. A conta que eles fecham é exata nas seis combinações -- é por isso que
# `altura_da_fita` pode prometer 2 px de tolerância contra o widget montado em vez de "mais ou
# menos isso".

MOLDURA_DO_BOTAO = 14
"""Borda mais preenchimento vertical de um `ttk.Button`, somando os dois lados.

**A folha de base da S-441 não mexe nisto, e a medição é a razão.** O `padding` de `TButton` sob
`bootstrap-light` já vem `10 4` de fábrica -- a folha cobre quem o tema deixou vazio, e o botão não
é um deles. Enquanto for assim, este 14 continua sendo medida do widget e não de uma escala."""

FOLGA_ACIMA_DO_ROTULO = 4
"""O vão que o `compound=TOP` abre entre o ícone e a primeira linha do rótulo."""

MOLDURA_DO_CABECALHO = 4
"""Borda mais preenchimento vertical do `ttk.Label` que desenha o nome do grupo."""


def espaco_ate_o_cabecalho(densidade: str, *, base: int = tipografia.BASE_DE_REFERENCIA) -> int:
    """O vão entre a fila de botões e o cabeçalho do grupo. **Altura: entra no orçamento.**

    Era um `dict` cravado aqui, com 2 e 0. A S-228 já o deixou como parâmetro dizendo que o eixo
    inteiro seria da S-232, e é isto: o número sai de `tipografia.folga`, e passa a acompanhar a
    fonte do sistema junto com o resto do espaço da janela. Na densidade compacta ele vale 1 e não
    0, pelo piso de `folga` -- dois vizinhos colados viram um controle só para o olho.
    """
    return tipografia.folga(tipografia.FOLGA_MINIMA, base=base, densidade=densidade)


def espaco_entre_botoes(densidade: str, *, base: int = tipografia.BASE_DE_REFERENCIA) -> int:
    """O `padx` entre dois botões do mesmo grupo. Largura, e não altura: não entra no orçamento.

    Mesmo papel de folga do vão do cabeçalho, e é de propósito que os dois saiam da mesma chamada:
    são o mesmo espaço -- "entre dois vizinhos do mesmo grupo" -- medido em direções diferentes.
    """
    return tipografia.folga(tipografia.FOLGA_MINIMA, base=base, densidade=densidade)


def quebrar_rotulo(texto: str, *, linhas: int = LINHAS_DO_ROTULO) -> str:
    """O rótulo repartido em até `linhas` linhas, na fronteira de palavra.

    Pura, e por isso conferível sem abrir janela -- e é o que permite afirmar que **nenhuma
    palavra some**: o `ttk.Button` não aceita `wraplength` (é opção de `tk.Button` e de `Label`),
    então quem reparte é este módulo, e não o widget.
    """
    palavras = str(texto).split()
    if len(palavras) <= 1 or linhas <= 1:
        return str(texto)
    largura = max(len(palavra) for palavra in palavras)
    largura = max(largura, -(-sum(len(p) + 1 for p in palavras) // linhas))
    montadas: list[str] = []
    for palavra in palavras:
        if montadas and len(montadas[-1]) + 1 + len(palavra) <= largura:
            montadas[-1] = f"{montadas[-1]} {palavra}"
        else:
            montadas.append(palavra)
    return "\n".join(montadas)


def altura_da_fita(
    modo: str,
    *,
    linha_de_texto: int,
    linha_de_apoio: int,
    densidade: str = pele.CONFORTAVEL,
    base: int = tipografia.BASE_DE_REFERENCIA,
) -> int:
    """A altura que a fita vai ocupar naquele modo, em pixel. **Pura** -- é o item.

    `linha_de_texto` e `linha_de_apoio` são o `linespace` das fontes de `CORPO` e de `AUXILIAR`,
    que é o que o Tk reporta e o que faz a conta acompanhar a fonte do sistema (S-149) em vez de
    cravar pontos. Quem os lê do Tk é `altura_atual`; quem os passa à mão é o teste, e é isso que
    permite afirmar o orçamento em 9, 10 e 12 pt sem trocar a fonte do Windows.

    **Nada de `winfo_height` no critério.** Um orçamento medido no widget montado só falha depois
    de a janela estar errada, e numa largura que o teste por acaso tenha escolhido. Aqui ele falha
    na conta, que é onde a decisão está.

    Levanta `KeyError` para modo ou densidade que não existem, como `tokens.cor`: um modo escrito
    errado que caísse no pleno devolveria um número plausível para o orçamento errado.
    """
    if modo not in LADO_DO_ICONE:
        raise KeyError(f"modo de fita desconhecido: {modo!r}. Os válidos estão em MODOS.")
    if densidade not in pele.DENSIDADES:
        raise KeyError(f"densidade desconhecida: {densidade!r}. As válidas estão em pele.DENSIDADES.")

    lado = LADO_DO_ICONE[modo]
    rotulo = LINHAS_DO_ROTULO * linha_de_texto
    if modo == COMPACTO:
        # Ícone **ao lado** do rótulo: a altura é a do mais alto dos dois, e não a soma. E o
        # cabeçalho não entra porque ele virou dica -- é daí que vem quase toda a economia.
        return max(lado, rotulo) + MOLDURA_DO_BOTAO

    botao = lado + FOLGA_ACIMA_DO_ROTULO + rotulo + MOLDURA_DO_BOTAO
    return botao + espaco_ate_o_cabecalho(densidade, base=base) + linha_de_apoio + MOLDURA_DO_CABECALHO


@dataclass(frozen=True)
class GrupoDeFita:
    """Um grupo desenhado: o cabeçalho e os comandos dele, na ordem do catálogo."""

    grupo: str
    """A chave em `comandos.GRUPOS`."""

    rotulo: str
    """O cabeçalho, como a pessoa lê -- `comandos.rotulo_do_grupo`."""

    itens: tuple[comandos.Comando, ...]
    """Os comandos com ícone daquele grupo. Nunca vazio: grupo vazio não vira `GrupoDeFita`."""


def grupos() -> tuple[GrupoDeFita, ...]:
    """A fita como dado: um grupo por cabeçalho, na ordem de `comandos.GRUPOS`.

    **Grupo sem comando visível não aparece**, e não aparece como cabeçalho vazio: um título
    solto é pior que a ausência dele -- ele promete um grupo e entrega uma faixa em branco.
    """
    montados = [
        GrupoDeFita(
            grupo=grupo,
            rotulo=comandos.rotulo_do_grupo(grupo),
            itens=tuple(registro for registro in comandos.do_grupo(grupo) if registro.icone),
        )
        for grupo in comandos.GRUPOS
    ]
    return tuple(pronto for pronto in montados if pronto.itens)


def acoes_da_fita() -> list[str]:
    """Os nomes dos comandos que a fita desenha, na ordem em que ela os desenha."""
    return [registro.acao for grupo in grupos() for registro in grupo.itens]
