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
a paleta e os atalhos.

**O corte do Tk foi feito em 2026-08-31 (S-506), e este pacote passou a ser a janela.** Saíram o
`app_tkinter.py`, 28 módulos de `ui/` acoplados ao toolkit e 46 arquivos de teste; o PyQt6 deixou
de ser o extra `qt` e virou dependência de base. O que ainda é Tk, de propósito, é
`cli/texto_transcrever.py` -- ferramenta de desenvolvimento com entrada própria, que não abre pelo
`.exe`.

**O que o corte deixou sem dono voltou depois, e vale a lista porque o padrão se repete.** Cada um
destes era uma decisão que sobreviveu em `ui/` sem ninguém para chamá-la, e nenhum quebrava teste:

- o **estado da janela** (`ui/state.py`): último livro, página, zoom, geometria, divisor e aba;
- o submenu **Abrir recente**, que sai do mesmo histórico;
- **Aparência** e **Densidade**, que o menu desenhava marcadas sobre um `lambda: None`;
- a **fila** e a **fita** -- os dois cromos que aquelas peles pedem (`qt/fila.py`, `qt/fita.py`);
- o **conjunto de peças** (`ui/conjuntos.py`), incluindo o traço engrossado de `ui/pecas.py`;
- o **árbitro do `Ctrl+Z`** (`ui/desfazivel.py`), que decide entre tabuleiro, texto e sala;
- os **códigos 1, 3, 4 e 5** do `--selftest`, que o `app_tkinter.py` devolvia.

A lição, e ela é a mesma da conta do catálogo: ao apagar uma camada, o que some em silêncio não é o
código -- é o **chamador** da decisão que ficou.

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
o PyQt5 já não publica roda para 3.13. **Ele deixou de ser o extra `qt` no dia do corte** (S-506):
o programa não abre sem ele, e uma dependência sem a qual o programa não abre não é opcional.
"""

from __future__ import annotations

__all__ = [
    "BarraFluida",
    "ControladorDeTreino",
    "DialogoDeBases",
    "DialogoDeEscopo",
    "DialogoDePartidas",
    "Exportador",
    "Fila",
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
    "Fila": "fila",
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


BASE_DOS_DIALOGOS = "QDialog"
"""A classe do Qt de onde toda janela de diálogo deste pacote desce. Ver `dialogos_do_produto`."""

BASES_DE_DIALOGO_DO_QT: frozenset[str] = frozenset(
    {
        BASE_DOS_DIALOGOS,
        "QColorDialog",
        "QErrorMessage",
        "QFileDialog",
        "QFontDialog",
        "QInputDialog",
        "QMessageBox",
        "QProgressDialog",
        "QWizard",
    }
)
"""Toda classe do Qt que **é** um `QDialog`, e não só a base direta (F9-C14).

**Um dos três buracos que o crítico do ciclo 13 abriu na varredura.** Ele escreveu
`class X(QMessageBox)` dentro de `qt/` e o portão de teclado passou calado: `QMessageBox` desce
de `QDialog` no Qt, mas a árvore sintática só vê o nome escrito na linha da classe. Uma janela de
mensagem com classe própria é uma tela de diálogo como qualquer outra.

A lista é do Qt e não deste produto -- ela só cresce quando o Qt ganha um diálogo novo --, e é
curta o bastante para ser lida inteira."""


def dialogos_do_produto(pasta: object | None = None) -> tuple[str, ...]:
    """Todo `QDialog` que este pacote define, **achado no código** e não declarado (F9-C12).

    **Por que uma varredura e não uma tabela.** Uma tabela escrita à mão tem a doença que o
    ciclo 9 e o ciclo 11 reprovaram nesta frente, um andar acima: quem acrescentar o décimo
    terceiro diálogo não vem aqui atualizá-la, e o portão de teclado voltaria a publicar
    `0 sem nome` sobre doze janelas de treze -- que é literalmente o defeito do ciclo 11 com o
    número trocado. O portão lê **esta** lista (`caissa.ui.audit.teclado.dialogos_registrados`),
    do mesmo jeito que lê `ui/pele.PELES` para saber quantas peles existem; a diferença é que
    aqui não há um menu a ler, então a fonte é o próprio código.

    **Lida da árvore sintática, e não por importação, e a razão é onde o portão roda.** O venv
    da suíte que guarda esta frente **não tem binding de Qt nenhum** -- foi por isso que a folha
    de estilo saiu de `qt/` para `ui/` --, e o teste que compara a lista do arnês com a do
    produto tem de rodar lá. Uma varredura que importasse `PyQt6` deixaria esse teste pulado,
    que é o mesmo que não existir. `ast` lê o arquivo; `class X(QDialog)` é um fato do texto.

    O fecho é **transitivo dentro do pacote**: uma classe que herde de outra que herde de
    `QDialog` entra. É o que faz a resposta continuar certa no dia em que alguém escrever uma
    base comum de diálogo aqui dentro.

    Devolve os nomes de classe em ordem alfabética, **incluindo os privados**: `_JanelaDeColar`
    é uma janela que a pessoa abre por `Estudo ▸ Colar`, e o sublinhado diz de quem é o código,
    não se a superfície existe.

    **Os três buracos que o crítico do ciclo 13 abriu, e os três fechados** (F9-C14). Ele
    sabotou a varredura de três jeitos e o portão passou calado nos três:

    1. `Base = QDialog` no módulo e `class X(Base)` -- resolvido por `_apelidos`, que segue a
       atribuição simples de nome para nome;
    2. `class X(QMessageBox)` -- resolvido por `BASES_DE_DIALOGO_DO_QT`, que lista as classes do
       Qt que **são** diálogos e não só a base direta;
    3. um `QDialog` num submódulo (`qt/<pasta>/novo.py`) -- resolvido por `rglob`, porque
       `glob("*.py")` não desce.

    **O que ela continua não podendo achar, e o portão passou a dizer**: um `QDialog` construído
    **em linha**, sem classe (`painel_de_estudo.ampliar_recorte`, S-282). Não há classe para a
    árvore sintática ler, e por isso a frase que o portão publica diz "os N `QDialog` que o
    produto declara **como classe**". Quem alcança essa tela é o filtro de `QEvent.Show` de
    `qt/acessibilidade.py`, que não depende de lista nenhuma -- é a razão de a decisão morar lá.
    """
    import ast
    from pathlib import Path

    raiz = Path(pasta) if pasta is not None else Path(__file__).resolve().parent
    bases_de: dict[str, set[str]] = {}
    for arquivo in sorted(raiz.rglob("*.py")):
        try:
            arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):  # pragma: no cover - árvore quebrada não é lista vazia
            continue
        apelidos = _apelidos(arvore)
        for no in ast.walk(arvore):
            if not isinstance(no, ast.ClassDef):
                continue
            nomes: set[str] = set()
            for base in no.bases:
                if isinstance(base, ast.Name):
                    nomes.add(apelidos.get(base.id, base.id))
                elif isinstance(base, ast.Attribute):  # `QtWidgets.QDialog`
                    nomes.add(apelidos.get(base.attr, base.attr))
            bases_de.setdefault(no.name, set()).update(nomes)

    achados = {nome for nome, bases in bases_de.items() if bases & BASES_DE_DIALOGO_DO_QT}
    while True:  # o fecho: quem herda de um diálogo também é um diálogo
        crescido = {
            nome for nome, bases in bases_de.items() if bases & achados
        } | achados
        if crescido == achados:
            return tuple(sorted(achados))
        achados = crescido


def _apelidos(arvore: object) -> dict[str, str]:
    """`apelido -> nome verdadeiro`, para `Base = QDialog` seguido de `class X(Base)`.

    Só atribuição simples de **um nome a um nome**, no nível do módulo ou dentro dele: é a forma
    que a sabotagem (d) do ciclo 13 usou, e é a única que se pode afirmar lendo o texto. Uma
    cadeia (`A = QDialog; B = A`) é seguida até parar, com teto no tamanho da tabela para que um
    ciclo escrito à mão (`A = B; B = A`) não vire laço infinito num portão.
    """
    import ast

    direto: dict[str, str] = {}
    for no in ast.walk(arvore):  # type: ignore[arg-type]
        if not isinstance(no, ast.Assign) or len(no.targets) != 1:
            continue
        alvo, valor = no.targets[0], no.value
        if isinstance(alvo, ast.Name) and isinstance(valor, ast.Name):
            direto[alvo.id] = valor.id
        elif isinstance(alvo, ast.Name) and isinstance(valor, ast.Attribute):
            direto[alvo.id] = valor.attr
    resolvidos: dict[str, str] = {}
    for apelido in direto:
        visto, atual = {apelido}, direto[apelido]
        while atual in direto and atual not in visto and len(visto) <= len(direto):
            visto.add(atual)
            atual = direto[atual]
        resolvidos[apelido] = atual
    return resolvidos
