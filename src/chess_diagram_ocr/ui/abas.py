"""O rótulo de uma aba, e quanto trabalho ela carrega (S-162).

**O problema.** Seis abas dizendo só o nome. Quanto há para fazer em cada uma -- 129 pendentes na
Revisão, 3.936 linhas no Dataset, 1.480 diagramas na Galeria -- é informação que só aparecia
**depois** de clicar, e é justamente ela que decide qual aba abrir.

**Por que o rótulo é função pura.** Porque a decisão está nos casos de borda, e são três: sem
contagem conhecida (a aba nunca foi carregada), contagem zero (que **não** vira "(0)": uma fila
vazia é um estado bom, e anunciá-lo com um zero entre parênteses é ruído permanente) e o milhar em
pt-BR, que é ponto e não vírgula.

**E o rótulo mudou de dono.** O `AppState` guarda a aba aberta pelo **rótulo** desde a S-156, e um
rótulo que agora carrega número deixaria de casar assim que a contagem mudasse -- a sessão seguinte
cairia na primeira aba, em silêncio. `nome_base` é o que separa as duas coisas: o nome é a
identidade, a contagem é o estado.
"""

from __future__ import annotations

from . import formato

__all__ = ["ABA_DE_TRABALHO", "contagem_no_rotulo", "nome_base", "rotulo"]

ABA_DE_TRABALHO = "Resultado"
"""Onde a janela abre num checkout novo (S-162).

Era a Configuração: três caminhos de arquivo e os parâmetros de treino, isto é, a aba do primeiro
dia e quase nunca depois. O trabalho começa no Resultado, que é onde o diagrama clicado na página
aparece."""


def rotulo(nome: str, contagem: int | None = None) -> str:
    """`Revisão (129)`, ou só `Revisão` quando não há número que importe.

    `None` é "ainda não sei" -- a aba que nunca carregou --, e `0` é "não há nada aqui". Os dois
    ficam sem parênteses, e a razão é a mesma: o parêntese existe para dizer *quanto falta*.
    """
    limpo = str(nome).strip()
    if not contagem:
        return limpo
    return f"{limpo} ({formato.inteiro(contagem)})"


def nome_base(texto: str) -> str:
    """O nome da aba sem a contagem: `Revisão (129)` → `Revisão`.

    É o que o `AppState` guarda e o que `rolagem.selecionar_aba` compara. Sem isto, lembrar a aba
    aberta entre execuções (S-156) pararia de funcionar no dia em que a fila mudasse de tamanho --
    e falharia em silêncio, caindo na primeira aba.
    """
    limpo = str(texto).strip()
    if limpo.endswith(")") and " (" in limpo:
        return limpo.rsplit(" (", 1)[0].strip()
    return limpo


def contagem_no_rotulo(texto: str) -> int | None:
    """A contagem que o rótulo mostra, ou `None`. Existe para o teste ler o que a tela diz."""
    limpo = str(texto).strip()
    if not (limpo.endswith(")") and " (" in limpo):
        return None
    numero = limpo.rsplit(" (", 1)[1][:-1].replace(".", "")
    return int(numero) if numero.isdigit() else None
