"""O que o visualizador de PDF decide fora do widget (S-31/S-69/S-330/S-503).

Três números medidos e o leitor do sistema. Nenhum deles toca toolkit, e os três
números são o tipo de constante que uma segunda implementação copia com o valor certo e o
significado errado:

- **`MIN_SELECTION_PX` é medida da folha, e não da tela** (S-330). A comparação era feita nas
  coordenadas do canvas, que já vêm multiplicadas pelo zoom: a 25% o piso valia 48 px de página, e
  a 200%, 6 px. O mesmo arrasto era "muito pequeno" numa vista e recorte válido na outra.
- **`CLICK_SLOP_PX` é o que separa clique de arrasto**, e é ele que deixa a rolagem pela mão
  conviver com os diagramas marcados: sem folga, o clique de quem apoia a mão vira arrasto e não
  abre diagrama nenhum; com folga demais, arrastar a barra abriria um diagrama por acidente.
- **`PASSO_DE_ZOOM` é aditivo**, e não multiplicativo: um clique, um passo previsível.

**`open_in_system_reader` tem três ramos, e é de propósito.** Sem o WebView2 (S-69) não sobrou
nada de específico de Windows no projeto, e deixar um `os.startfile` sozinho reintroduziria a
dependência de plataforma pela porta dos fundos -- por um botão.

**A cor da caixa não mora mais aqui.** Quem diz em que ponto do trabalho um diagrama está é
`page_overlay.estado_da_caixa`, que é pura e é a mesma dos dois lados; a cor daquele estado é um
papel de `tokens`, e `qt/visor.py` a resolve contra a pele em uso por `tema.cor_atual`. Os quatro
apelidos `BOX_OUTLINE*` e o `box_color` que os escolhia davam **cor literal** ao `tk.Canvas`, que
não conhecia papel -- e saíram na triagem da S-511, pelo mesmo argumento que apagou os doze
apelidos de cor de `desenho_do_tabuleiro.py`.

`ui/pdf_panel.py` reexportava tudo o que está aqui, e saiu no corte do Tk (S-506). Quem consome
agora é `qt/painel_do_pdf.py` e `qt/visor.py`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

__all__ = [
    "CLICK_SLOP_PX",
    "MIN_SELECTION_PX",
    "PASSO_DE_ZOOM",
    "SEM_CONTEUDO",
    "frase_de_abertura",
    "SELECTION_HALO_PX",
    "open_in_system_reader",
]

PASSO_DE_ZOOM = 0.1
"""Quanto um clique em `+` ou `-` muda o zoom. Aditivo, e não multiplicativo: um clique, um passo
previsível."""

MIN_SELECTION_PX = 12
"""Arrasto menor que isto é clique errado, não seleção. Abaixo disso o recorte não conteria nem
uma casa do tabuleiro.

**Doze pixels de página, e não de tela (S-330).** O que a constante quer dizer -- "menos que isto
não contém casa nenhuma" -- é uma afirmação sobre a folha, então é na folha que ela se mede."""

CLICK_SLOP_PX = 4
"""Quanto o ponteiro pode andar entre apertar e soltar e ainda ser um clique.

Sem folga, o clique de quem apoia a mão no mouse vira arrasto e não abre diagrama nenhum; com
folga demais, arrastar a barra de rolagem abriria um diagrama por acidente."""

SELECTION_HALO_PX = 4
"""Folga da segunda borda do diagrama selecionado, para fora da caixa.

Para **fora** porque a caixa encosta no diagrama: uma borda por dentro cairia sobre as casas da
primeira fila, e a caixa existe justamente para conferir a posição."""

def open_in_system_reader(pdf_path: Path) -> None:
    """Abre o PDF no leitor padrão do sistema, na janela dele.

    Substitui o WebView2 embutido (S-69) e cabe em oito linhas porque não tenta ser uma aba: quem
    quer ler o livro ganha o leitor de verdade, com rolagem contínua e busca de texto, e o app não
    promete saber o que acontece lá dentro -- que era a promessa que a aba "Leitura" não tinha como
    cumprir.

    Os três ramos existem porque, sem o WebView2, **não sobrou nada de específico de Windows no
    projeto**. Deixar um `os.startfile` sozinho aqui reintroduziria a dependência de plataforma
    pela porta dos fundos, e por um botão.
    """
    alvo = str(Path(pdf_path).resolve())
    if sys.platform == "win32":
        # `os.startfile` só existe no Windows -- daí o `getattr`, que mantém os três ramos
        # verificáveis nas três plataformas em vez de depender de um `type: ignore`.
        getattr(os, "startfile")(alvo)  # noqa: B009
    elif sys.platform == "darwin":
        subprocess.Popen(["open", alvo])
    else:
        subprocess.Popen(["xdg-open", alvo])


# ----------------------------------------------------- por que o livro não abriu, em pt-BR

SEM_CONTEUDO = "está vazio (0 byte)"
"""O que dizer de um arquivo de tamanho zero. Separado porque é a causa mais comum de todas: um
download interrompido, ou uma cópia de rede que não terminou."""

_CAUSAS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("empty file", "empty pdf"), SEM_CONTEUDO),
    (("no such file", "not a file", "cannot find"), "não foi encontrado"),
    (("permission", "denied"), "não pôde ser lido: o sistema negou a permissão"),
    (("is a directory",), "é uma pasta, e não um arquivo"),
    (
        ("failed to open", "cannot open", "format error", "syntax error", "damaged", "no objects found"),
        "não é um PDF que este programa consiga ler: ele está corrompido, truncado, ou não é um PDF",
    ),
)
"""`(pistas na mensagem da biblioteca) -> a frase em pt-BR`.

**Por padrão de texto e não por tipo**, pela mesma razão de `cli._TRADUCOES`: o PyMuPDF levanta
`FileDataError` para o arquivo corrompido, `EmptyFileError` para o vazio e `RuntimeError` cru para
metade do resto, e esses nomes mudam entre versões. O que não muda é a frase que ele escreve."""


def frase_de_abertura(nome: str, erro: BaseException) -> str:
    """Por que o livro não abriu, em pt-BR e nomeando o **arquivo** -- não o caminho escapado.

    **O defeito medido pelo crítico em 2026-09-05** (S-528, segunda rodada). Um PDF truncado abria
    a caixa "Falha ao abrir X.pdf" com o texto da biblioteca embaixo: `Failed to open file
    'C:\\Users\\AMD\\...'` -- em inglês, com o caminho escapado duas vezes, e repetindo um nome de
    arquivo que a primeira linha já dava. Um arquivo vazio dizia `Cannot open empty file`.

    **Aqui e não em `pdf_io`**, e a razão tem duas metades. A primeira é a fronteira deste projeto:
    "por que não abriu" é decisão -- que frase a pessoa lê --, e decisão mora em `ui/`. A segunda é
    medida: `pdf_io` é módulo do **caminho de medição de campo**, e `field_eval.measurement_
    fingerprint` grava o digest dele em cada relatório de `docs/metrics/`; mexer numa linha de lá
    invalida os quatro relatórios correntes e obriga a remedi-los, o que este item não pede.

    **E os comandos de linha já estavam cobertos**: `cli.message_for` traduz "failed to open" desde
    a S-126. Quem não tinha tradução nenhuma era a **janela**, e é ela que chama isto.

    **O texto original não vai para a tela**, ao contrário de `cli.message_for`, e a diferença é o
    destinatário: lá quem lê é quem rodou um comando num terminal e vai pesquisar a mensagem; aqui
    é quem clicou em "Abrir PDF", e para essa pessoa o caminho escapado é ruído sobre uma pasta que
    ela acabou de escolher. O original fica no log.

    Uma recusa que **já** é nossa passa intacta: é o caso do PDF protegido por senha (S-331), cuja
    frase `pdf_io` escreve em pt-BR e começa pelo nome do arquivo.
    """
    texto = str(erro)
    if texto.startswith(nome) or texto.startswith("O PDF recebido"):
        return texto
    baixo = texto.lower()
    for pistas, causa in _CAUSAS:
        if any(pista in baixo for pista in pistas):
            return f"{nome} {causa}."
    return f"{nome} não pôde ser aberto ({type(erro).__name__})."
