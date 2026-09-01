"""A janela em PyQt6 -- o frontend que vai substituir o Tk (S-500/S-502).

**O que este pacote é.** A interface sobre exatamente o mesmo `service.py` que o
`app_tkinter.py` usa. Ele **nasceu** como versão de teste, para responder com código que roda
três perguntas que só uma segunda implementação responde --

1. *A fronteira da S-31 aguenta outro frontend?* O `OcrService` foi extraído com a promessa de
   que a interface é apresentação. Um segundo frontend é o teste dessa promessa, e ele achou o
   que faltava: nada aqui importa `tkinter`, e nada em `service.py`, `detection/`,
   `page_overlay.py` ou `viewport.py` precisou mudar para isto existir.
2. *Quanto da lógica de tela já estava fora do Tk?* Muito: `ui/page_overlay.py` (onde estão as
   caixas, o que um clique nelas significa, como cada estado se desenha) e `ui/viewport.py` (o
   que a roda faz, para onde o zoom puxa, o que "caber na página" quer dizer) são reusados
   inteiros. O que este pacote escreve do zero é só o desenho -- `QPainter` no lugar de
   `create_rectangle`.
3. *O que o Tk estava carregando sozinho?* O que **não** dá para reusar aparece aqui como
   código novo, e é o inventário honesto do que uma migração custaria.

**O que ele faz.** Abre o livro, navega, marca os diagramas sobre a página, lê a página, mostra
o que leu -- tabuleiro, FEN, confiança, lado a jogar e legalidade -- e **corrige e grava**.

**Os sete painéis do produto estão portados (S-503/S-504)**: Resultado, PDF, Galeria, Estudo,
Dataset, Revisão e Texto, mais a fita, a paleta de comandos e os quatro diálogos. Cada um tem o
seu `tests/test_qt_*.py`.

**E a janela os reúne (S-505).** `JanelaPrincipal` monta as seis abas de trabalho ao lado do
visualizador, liga sinal a sinal e soma as três tabelas de comandos numa só, de onde saem o menu,
a paleta e os atalhos. O que falta agora é o **corte do Tk**, e ele é decisão do dono: enquanto
não vier, os dois frontends abrem o mesmo `service.py` e nada do lado do Tk é apagado.

---

**Este pacote deixou de ser uma versão de teste, e a mudança tem data.** Até 2026-08-31 ele era
somente-leitura por decisão, e o parágrafo acima terminava assim:

    ...e para de propósito antes do que a janela do produto tem além disso: editar casa a casa,
    salvar amostra, treinar, exportar PGN, galeria, estudo e a aba de texto. Um teste que
    escrevesse no `labels.csv` deixaria de ser um teste.

Aquilo era certo enquanto o pacote existia para **provar** uma fronteira. O dono decidiu que o Qt
substitui o Tk, e a decisão muda o argumento: uma janela que vai ser a única não pode recusar o
gesto mais repetido do programa -- corrigir, `Ctrl+S`, seta. O que continua valendo é a cautela
que estava por trás da regra, e ela é atendida por outro caminho: **quem decide o que "salvar"
significa não é este pacote.** `ui/editor_model.DiagramEditorModel.save_target()` responde
"amostra nova ou regravar a linha existente?" -- a regra mais delicada da interface, pura e com
teste sem janela desde a S-49 -- e os dois frontends a obedecem. O risco que a S-500 evitava era
um **segundo caminho de escrita**; o que existe é um segundo widget sobre o mesmo caminho.

**As três perguntas continuam respondidas, e a resposta é o que tornou a decisão possível.**
`ui/page_overlay.py`, `ui/viewport.py`, `ui/board_model.py`, `ui/board_edit.py`,
`ui/editor_model.py` e as tabelas de `ui/atalhos.py`, `ui/comandos.py` e `ui/tabela.py` são
reusados inteiros -- é por isso que a migração é um porte de desenho, e não uma reescrita.

**Por que PyQt6 e não PyQt5.** É o que tem suporte na faixa `>=3.10,<3.14` do projeto inteira;
o PyQt5 já não publica roda para 3.13. A dependência ainda é o extra `qt` do `pyproject.toml`, e
**isso muda quando o corte acontecer**: no dia em que o `app_tkinter.py` sair, o PyQt6 deixa de
ser extra e passa a ser dependência de base, porque o programa não abre sem ele.
"""

from __future__ import annotations

__all__ = [
    "BarraFluida",
    "ControladorDeTreino",
    "DialogoDeBases",
    "DialogoDeEscopo",
    "DialogoDePartidas",
    "Exportador",
    "Fita",
    "GuardaDeAtalhos",
    "JanelaDaPaleta",
    "JanelaDeAtalhos",
    "JanelaDeBusca",
    "JanelaPrincipal",
    "PainelDeCampo",
    "PainelDaGaleria",
    "PainelDeEstudo",
    "PainelDeResultado",
    "PainelDeRevisao",
    "PainelDeTexto",
    "PainelDoDataset",
    "PainelDoPdf",
    "RodapeDaJanela",
    "TabelaQt",
    "TabuleiroDeJogo",
    "TabuleiroEditavel",
    "TabuleiroQt",
    "Tarefa",
    "VisorDePagina",
    "aplicar_tema",
    "cor_atual",
    "fonte_atual",
    "pixmap_de_rgb",
    "qimage_de_rgb",
]

_POR_MODULO: dict[str, str] = {
    "BarraFluida": "barra",
    "Fita": "fita",
    "ControladorDeTreino": "dialogos",
    "DialogoDeBases": "dialogos",
    "DialogoDeEscopo": "dialogos",
    "DialogoDePartidas": "dialogos",
    "Exportador": "exportador",
    "GuardaDeAtalhos": "atalhos",
    "JanelaDaPaleta": "paleta",
    "JanelaDeAtalhos": "legenda",
    "JanelaDeBusca": "painel_de_texto",
    "JanelaPrincipal": "janela",
    "PainelDeCampo": "campo",
    "PainelDoDataset": "painel_do_dataset",
    "PainelDaGaleria": "painel_da_galeria",
    "PainelDoPdf": "painel_do_pdf",
    "PainelDeEstudo": "painel_de_estudo",
    "PainelDeResultado": "painel_de_resultado",
    "TabuleiroDeJogo": "tabuleiro_de_jogo",
    "PainelDeRevisao": "painel_de_revisao",
    "PainelDeTexto": "painel_de_texto",
    "RodapeDaJanela": "rodape",
    "TabelaQt": "tabela",
    "TabuleiroEditavel": "tabuleiro_editavel",
    "TabuleiroQt": "tabuleiro",
    "Tarefa": "trabalho",
    "VisorDePagina": "visor",
    "aplicar_tema": "tema",
    "cor_atual": "tema",
    "fonte_atual": "tema",
    "pixmap_de_rgb": "imagens",
    "qimage_de_rgb": "imagens",
}
"""`nome exportado -> módulo em que ele mora`, para o `__getattr__` abaixo.

Uma tabela e não uma cadeia de `if`: com onze nomes a cadeia já era mais longa que a tabela, e
cada nome novo pedia três linhas em vez de uma -- que é a forma de esquecer o `__all__`. O teste
compara os dois lados, então um nome exportado e não mapeado falha na suíte."""


def __getattr__(nome: str) -> object:
    """Importa sob demanda, para que `import chess_diagram_ocr.qt` não exija o PyQt6.

    A guarda do `app_pyqt.py` diz em pt-BR o que instalar quando a biblioteca falta; um
    `ImportError` disparado na importação do pacote chegaria antes dela, em inglês, e com o
    rastro apontando para este arquivo em vez de para a instalação.
    """
    modulo = _POR_MODULO.get(nome)
    if modulo is None:
        raise AttributeError(f"module {__name__!r} has no attribute {nome!r}")
    from importlib import import_module

    return getattr(import_module(f"{__name__}.{modulo}"), nome)
