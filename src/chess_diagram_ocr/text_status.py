"""O que do plano de reconhecimento de texto já existe no disco (S-178 a S-217).

**O defeito que isto evita.** O plano das Fases 25 a 31 tem 38 itens e atravessa sete fases. Um
plano desse tamanho envelhece de um jeito específico: alguém entrega metade de um item, marca
`✅ implementada` no documento, e três semanas depois ninguém sabe se o que está escrito descreve
o disco ou a intenção de quem escreveu. A `SPEC_UI` e a `SPEC_FASE14` são prova de que o formato
funciona quando alguém o mantém à mão -- e a S-134 é prova de que ninguém mantém.

**Por que a fonte é o disco, e não o documento.** O critério de "existe" tem de ser verificável
sem opinião. Aqui ele é uma **sonda**: um arquivo que precisa estar no lugar, um símbolo que
precisa estar definido num módulo, uma chave que precisa estar no `pyproject`. O documento diz o
que se pretende; a sonda diz o que há. `tests/test_text_status.py` falha quando os dois
discordam, que é a única forma de a marcação do documento continuar significando alguma coisa.

**Nada aqui importa o que sonda.** Um `import chess_diagram_ocr.text.recognizer` puxaria `torch`
e o extra `texto`, e o comando passaria a exigir o ambiente que ele existe para dizer se está
montado. Símbolo é procurado com `ast` sobre o arquivo -- estático, barato, e funciona em clone
limpo sem nenhuma dependência instalada.

**O que uma sonda atendida não prova.** Ela prova que o código foi escrito, não que ele funciona:
o critério de aceite de cada item está na `docs/SPEC_TEXTO.md` e quem o verifica é a suíte. Um
item ✅ aqui com testes vermelhos é um item quebrado, e é por isso que a saída do comando diz
"sonda atendida" e nunca "item pronto".
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
"""A raiz do repositório: `src/chess_diagram_ocr/text_status.py` sobe dois níveis."""

SPEC = "docs/SPEC_TEXTO.md"
ROADMAP = "docs/ROADMAP_TEXTO.md"

ESTADOS = ("feito", "parcial", "pendente")

SIMBOLO_DE_ESTADO = {"feito": "✅", "parcial": "◐", "pendente": "⬜"}
"""Os mesmos três símbolos que a `docs/SPEC_TEXTO.md` usa no cabeçalho de cada seção."""

SIMBOLO_ASCII = {"feito": "[x]", "parcial": "[~]", "pendente": "[ ]"}
"""Para console que não encoda os de cima -- o `cmd.exe` em cp1252 é o caso, e é o console
padrão da máquina onde este projeto roda. Ver `cli/text_status._simbolos`."""


@dataclass(frozen=True)
class Item:
    """Um item do plano, com as sondas que dizem se ele existe.

    `sondas` é uma tupla porque um item quase nunca é um símbolo só -- a S-179 é a função de
    carga **e** o metadado no disco, e ter só um dos dois é o estado `parcial`, que é justamente
    o que se quer enxergar numa entrega pela metade.
    """

    id: str
    fase: int
    titulo: str
    sondas: tuple[str, ...]


MANIFESTO: tuple[Item, ...] = (
    # ---------------------------------------------------------------- Fase 25
    Item("S-178", 25, "O subpacote text/, e a procedência do que foi portado",
         ("arquivo:src/chess_diagram_ocr/text/PROCEDENCIA.md", "modulo:chess_diagram_ocr.text")),
    Item("S-179", 25, "O modelo de 292 classes entra pinado, ou não entra",
         ("simbolo:chess_diagram_ocr.text.modelo:carregar_classificador", "arquivo:models/char_meta.json")),
    Item("S-180", 25, "char_to_folder e folder_to_char portados sem uma linha de diferença",
         ("simbolo:chess_diagram_ocr.text.classes:char_to_folder",
          "simbolo:chess_diagram_ocr.text.classes:folder_to_char")),
    Item("S-181", 25, "GlyphRecognizer implementa TextRecognizer, e a S-43 não muda",
         ("simbolo:chess_diagram_ocr.text.recognizer:GlyphRecognizer",)),
    # A sonda era `pyproject:texto`, e a implementação a desmentiu: o extra sairia **vazio** --
    # o classificador traz `torch`, `opencv` e `pillow`, que já são dependências obrigatórias, e
    # `uv sync --extra texto` não instalaria nada. O que de fato porteia o recurso é o arquivo de
    # pesos, que não vem no repositório. Ver a seção da S-182 na SPEC_TEXTO.
    # A terceira sonda entrou em 2026-08-23, e o motivo e um defeito que so aparece quando o item
    # comeca a dar certo: `arquivo:models/char_classifier.pt` era **falso em todo clone** -- os
    # pesos nao vem no repositorio --, entao o item ficava `parcial` sozinho, sem que a sonda
    # medisse nada do que ele ainda deve. No dia em que a S-204 treinou o modelo, o arquivo
    # apareceu e o disco passou a dizer `implementada` para um item com dois criterios de aceite
    # ainda abertos. A sonda nova aponta para um deles -- a barra de status dizer qual dispositivo
    # o classificador de caracteres usa --, e por isso ela responde `nao` ate o item fechar de
    # verdade, com ou sem `.pt` no disco.
    Item("S-182", 25, "Onde moram os pesos, e o que o programa faz quando eles faltam",
         ("simbolo:chess_diagram_ocr.settings:ENV_OCR_GLYPH_MODEL", "arquivo:models/char_classifier.pt",
          "simbolo:chess_diagram_ocr.ui.estado_do_rodape:dispositivo_do_classificador_de_caracteres")),
    Item("S-183", 25, "O placar da faixa de legenda: camada de texto, RapidOCR e glifo",
         ("simbolo:chess_diagram_ocr.cli.texto_placar:main", "metrica:texto_faixa")),
    # ---------------------------------------------------------------- Fase 26
    Item("S-184", 26, "A binarização que decide pelo resultado, não pelo histograma",
         ("simbolo:chess_diagram_ocr.text.binarizacao:binarize",)),
    Item("S-185", 26, "O box de caractere, e a régua que separa respingo de ponto final",
         ("simbolo:chess_diagram_ocr.text.boxes:caixas_de_caractere",
          "simbolo:chess_diagram_ocr.text.boxes:escala_de_texto")),
    Item("S-186", 26, "O colado na horizontal, e o árbitro que confirma o corte",
         ("simbolo:chess_diagram_ocr.text.colados:separar", "metrica:texto_colados")),
    Item("S-187", 26, "A linha, e a ordem de leitura dentro dela",
         ("simbolo:chess_diagram_ocr.text.linhas:quebrar_em_linhas",)),
    Item("S-188", 26, "Ler a linha, e não o caractere",
         ("simbolo:chess_diagram_ocr.text.leitura_de_linha:em_bloco", "metrica:texto_linha")),
    Item("S-189", 26, "A confiança sai da concordância, e ela é calibrada",
         ("simbolo:chess_diagram_ocr.text.leitura_de_linha:confianca_por_concordancia",
          "metrica:texto_calibracao")),
    # ---------------------------------------------------------------- Fase 27
    Item("S-190", 27, "A calha: onde a coluna acaba, medido na imagem",
         ("simbolo:chess_diagram_ocr.text.colunas:calha",)),
    Item("S-191", 27, "A calha não morre por uma letra de cabeçalho",
         ("simbolo:chess_diagram_ocr.text.colunas:atribuir_coluna",)),
    Item("S-192", 27, "O parágrafo, o recuo, e a coluna estreita demais para ser coluna",
         ("simbolo:chess_diagram_ocr.text.paragrafos:cortar",)),
    Item("S-193", 27, "O diagrama é um objeto da coluna, não um buraco nela",
         ("simbolo:chess_diagram_ocr.text.pagina:sequencia_de_leitura",)),
    Item("S-194", 27, "O placar da ordem de leitura",
         ("simbolo:chess_diagram_ocr.cli.texto_ordem:main", "metrica:texto_ordem")),
    # ---------------------------------------------------------------- Fase 28
    Item("S-195", 28, "A tarja: texto claro sobre escuro",
         ("simbolo:chess_diagram_ocr.text.negativo:candidatos",)),
    Item("S-196", 28, "A trama de meio-tom",
         ("simbolo:chess_diagram_ocr.text.trama:candidatos",)),
    # As sondas de código estão atendidas; a métrica só existe com o classificador de verdade --
    # a tabela dos quatro ângulos precisa de um árbitro, e o árbitro são os pesos que faltam.
    Item("S-197", 28, "O texto girado, que hoje sairia errado em silêncio",
         ("simbolo:chess_diagram_ocr.text.vertical:candidatos",
          "simbolo:chess_diagram_ocr.text.vertical:recorte_de_pe",
          "metrica:texto_vertical")),
    Item("S-198", 28, "O box que engoliu duas linhas",
         ("simbolo:chess_diagram_ocr.text.duas_linhas:partir", "metrica:texto_duas_linhas")),
    Item("S-199", 28, "A tabela sai como tabela",
         ("simbolo:chess_diagram_ocr.text.tabela:ler",)),
    # ---------------------------------------------------------------- Fase 29
    Item("S-200", 29, "O inventário, antes do primeiro treino",
         ("simbolo:chess_diagram_ocr.cli.texto_inventario:main", "metrica:texto_inventario")),
    # A terceira sonda das duas abaixo é o **dado**, e não o código, e ela entrou em 2026-08-23
    # pelo mesmo motivo que a terceira da S-182: sem ela os dois itens diriam `implementada` com
    # a metade que importa em aberto. `data/texto_procedencia.csv` é o arquivo que só o
    # `PyBoxEditor_Tkinter` pode produzir -- ele carrega quem rotulou (S-201) e de que livro
    # (S-203) --, e enquanto ele não existe nenhum número desta base separa rótulo humano de
    # palpite de modelo nem mede generalização de fonte. O código dos dois itens está pronto e
    # espera por ele.
    Item("S-201", 29, "A procedência: humano, modelo, ou não se sabe",
         ("simbolo:chess_diagram_ocr.text.dataset:procedencia_de", "metrica:texto_procedencia",
          "arquivo:data/texto_procedencia.csv")),
    # A sonda de `text.conflitos:achar` entrou em 2026-08-23 e nao substitui a de `dedupe`: sao
    # as duas metades do item. `conflitos` acha a copia **exata** (hash) e o que ela revelou --
    # a mesma imagem sob dois rotulos --, e `dedupe:agrupar` continua devendo a quase-duplicata,
    # que e o descritor de lado 24 com limiar 0,20. Marcar o item como feito com so a primeira
    # metade esconderia justamente a parte que ainda mede errado.
    Item("S-202", 29, "A duplicata exata, e a quase-duplicata",
         ("simbolo:chess_diagram_ocr.text.conflitos:achar", "simbolo:chess_diagram_ocr.text.dedupe:agrupar",
          "metrica:texto_dedupe")),
    Item("S-203", 29, "O split por livro, e a prova de que não vazou",
         ("simbolo:chess_diagram_ocr.text.dataset:split_por_livro", "metrica:texto_vazamento",
          "arquivo:data/texto_procedencia.csv")),
    Item("S-204", 29, "O treino do classificador de caracteres",
         ("simbolo:chess_diagram_ocr.cli.texto_train:main", "metrica:texto_treino",
          # A terceira entrou em 2026-08-23 com a grade de variantes: ela é o critério de aceite
          # que o item ficou devendo desde agosto, e sem sonda ele diria `implementada` com a
          # tabela por fazer -- que foi exatamente o estado dele por três semanas.
          "metrica:texto_variantes")),
    Item("S-205", 29, "A calibração entra no fim do treino, ou não sobrevive a ele",
         ("simbolo:chess_diagram_ocr.text.calibracao:calibrar", "metrica:texto_ece")),
    Item("S-206", 29, "O placar honesto: o classificador, e a página",
         ("metrica:texto_placar_final",)),
    # ---------------------------------------------------------------- Fase 30
    Item("S-207", 30, "O lado a jogar deixa de depender de motor de fora",
         ("simbolo:chess_diagram_ocr.text.lado:lado_por_glifo", "metrica:texto_lado")),
    Item("S-208", 30, "A notação validada pelas regras, e o PGN que sai dela",
         ("simbolo:chess_diagram_ocr.text.notacao:fatiar", "simbolo:chess_diagram_ocr.text.notacao:validar")),
    Item("S-209", 30, "O léxico sinaliza, e nunca troca",
         ("simbolo:chess_diagram_ocr.text.lexico:carregar", "arquivo:assets/lexico/idioma.txt.gz")),
    Item("S-210", 30, "A camada de texto invisível: o PDF pesquisável",
         ("simbolo:chess_diagram_ocr.text.pdf_pesquisavel:escrever_camada",)),
    Item("S-211", 30, "O modelo de página: coluna, bloco, linha, texto | diagrama | tabela",
         ("simbolo:chess_diagram_ocr.text.pagina:PaginaLida",)),
    # ---------------------------------------------------------------- Fase 31
    Item("S-212", 31, "A fila de revisão de caractere",
         ("simbolo:chess_diagram_ocr.text.fila:ordenar",)),
    Item("S-213", 31, "Aplicar a todos os semelhantes",
         ("simbolo:chess_diagram_ocr.text.semelhanca:semelhantes", "metrica:texto_semelhanca")),
    Item("S-214", 31, "A coleta em quarentena",
         ("simbolo:chess_diagram_ocr.text.coleta:coletar", "simbolo:chess_diagram_ocr.text.coleta:promover")),
    Item("S-215", 31, "O orçamento por página, e o teto que a varredura respeita",
         ("simbolo:chess_diagram_ocr.cli.texto_custo:main", "metrica:texto_custo")),
    # ------------------------------------------------- Fase 27, acrescentado depois (2026-08-23)
    # **Fica no fim porque o manifesto é ordenado por número, e não por fase.** É o que
    # `test_os_itens_sao_contiguos_e_unicos` cobra, e é a ordem certa: um item novo nasce no fim
    # da numeração mesmo quando pertence a uma fase antiga. O agrupamento na tela é pelo campo
    # `fase`, então ele sai sob a Fase 27, onde é o lugar dele.
    #
    # A sonda de código é `direcao_pela_numeracao`, e não `parece_grade`: a geometria separa grade
    # de prosa, mas quem responde à pergunta do item -- em que direção a grade se lê -- é o número
    # impresso. Um `parece_grade` sozinho no disco seria meio item marcado como inteiro.
    Item("S-216", 27, "A grade de exercícios, e a direção que só o número impresso diz",
         ("simbolo:chess_diagram_ocr.text.grade:direcao_pela_numeracao", "metrica:texto_grade")),
    # ------------------------------------------------- Fase 25, acrescentado depois (2026-08-23)
    # **Sai sob a Fase 25 porque foi a semeadura da S-183 que o desenterrou**, e é ao lado dela
    # que ele se lê. O código consertado é da S-16, que é de outra spec inteira -- mas o item
    # mora onde a medição que o achou mora, e não onde o `def` mora.
    #
    # A sonda de código é `is_diagram_font`, e não `_is_diagram_font_row`: o filtro já existia e
    # continuaria existindo com o defeito dentro, então a presença dele não prova nada. O que a
    # S-217 acrescenta é o crivo pelo **nome da fonte**, e é ele que a sonda procura.
    Item("S-217", 25, "O tabuleiro que é texto, nas duas codificações que o acervo tem",
         ("simbolo:chess_diagram_ocr.pdf_text:is_diagram_font", "metrica:texto_fonte_diagrama")),
)

TITULO_DA_FASE = {
    25: "A fronteira, e a prova de que o modelo atravessa",
    26: "Do pixel à linha",
    27: "A coluna",
    28: "Os casos que apagam texto",
    29: "A base de 608 mil",
    30: "O que o texto lido serve",
    31: "O que faz a base crescer",
}


class SondaInvalida(ValueError):
    """A sonda não tem uma das formas conhecidas.

    Levanta em vez de devolver `False`: uma sonda com erro de digitação que responde "não existe"
    é indistinguível de um item que não foi feito, e o item ficaria eternamente pendente sem que
    ninguém entendesse por quê. É a lição do `folder_to_char` que devolvia `"?"` em silêncio.
    """


def _caminho_do_modulo(pontilhado: str, raiz: Path) -> Path:
    """`chess_diagram_ocr.text.recognizer` -> `src/chess_diagram_ocr/text/recognizer.py`.

    Um pacote (`chess_diagram_ocr.text`) resolve para o `__init__.py` dele.
    """
    partes = pontilhado.split(".")
    base = raiz / "src" / Path(*partes)
    return base / "__init__.py" if base.is_dir() else base.with_suffix(".py")


def _define_no_topo(arquivo: Path, nome: str) -> bool:
    """O módulo define `nome` no nível de módulo?

    `ast` e não `import`: importar puxaria `torch` e o extra `texto`, e o comando passaria a
    exigir o ambiente que ele existe para descrever. Arquivo com erro de sintaxe conta como
    "não define" -- ele não importaria também.
    """
    try:
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):  # pragma: no cover - arquivo em edição
        return False

    for no in arvore.body:
        if isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and no.name == nome:
            return True
        if isinstance(no, ast.Assign):
            if any(isinstance(alvo, ast.Name) and alvo.id == nome for alvo in no.targets):
                return True
        if isinstance(no, ast.AnnAssign) and isinstance(no.target, ast.Name) and no.target.id == nome:
            return True
    return False


def _extras_do_pyproject(raiz: Path) -> set[str]:
    """As chaves de `[project.optional-dependencies]`, sem depender de um leitor de TOML.

    O mesmo leitor de dez linhas de `tests/test_docs.py`, e pelo mesmo motivo: `tomllib` é 3.11+
    e este projeto exige 3.10.
    """
    texto = (raiz / "pyproject.toml").read_text(encoding="utf-8")
    dentro = False
    chaves: set[str] = set()
    for linha in texto.splitlines():
        despida = linha.strip()
        if despida.startswith("["):
            dentro = despida == "[project.optional-dependencies]"
            continue
        if not dentro:
            continue
        achado = re.match(r"([A-Za-z0-9_-]+)\s*=", despida)
        if achado:
            chaves.add(achado.group(1))
    return chaves


def sonda_atendida(sonda: str, raiz: Path = RAIZ) -> bool:
    """Uma sonda, respondida contra o disco. Ver `SondaInvalida` para o que não é sonda.

    As cinco formas:

    - `modulo:pacote.modulo` -- o arquivo do módulo existe
    - `simbolo:pacote.modulo:Nome` -- o módulo define `Nome` no topo
    - `arquivo:caminho/relativo` -- existe (aceita `*`, para artefato com data no nome)
    - `metrica:prefixo` -- existe `docs/metrics/<prefixo>*.json`
    - `pyproject:extra` -- o extra está declarado
    """
    tipo, _, resto = sonda.partition(":")
    if not resto:
        raise SondaInvalida(f"sonda sem alvo: {sonda!r}")

    if tipo == "modulo":
        return _caminho_do_modulo(resto, raiz).is_file()

    if tipo == "simbolo":
        pontilhado, _, nome = resto.partition(":")
        if not nome:
            raise SondaInvalida(f"sonda de símbolo sem nome: {sonda!r}")
        arquivo = _caminho_do_modulo(pontilhado, raiz)
        return arquivo.is_file() and _define_no_topo(arquivo, nome)

    if tipo == "arquivo":
        if "*" in resto:
            return any(raiz.glob(resto))
        return (raiz / resto).exists()

    if tipo == "metrica":
        return any((raiz / "docs" / "metrics").glob(f"{resto}*.json"))

    if tipo == "pyproject":
        return resto in _extras_do_pyproject(raiz)

    raise SondaInvalida(f"tipo de sonda desconhecido: {tipo!r} em {sonda!r}")


@dataclass(frozen=True)
class Resultado:
    """O que as sondas de um item responderam."""

    item: Item
    atendidas: tuple[str, ...]
    faltando: tuple[str, ...]

    @property
    def estado(self) -> str:
        if not self.faltando:
            return "feito"
        return "parcial" if self.atendidas else "pendente"

    def simbolo(self, *, ascii_puro: bool = False) -> str:
        tabela = SIMBOLO_ASCII if ascii_puro else SIMBOLO_DE_ESTADO
        return tabela[self.estado]


def verificar(raiz: Path = RAIZ, *, fase: int | None = None) -> list[Resultado]:
    """O manifesto inteiro (ou uma fase) respondido contra o disco."""
    saida: list[Resultado] = []
    for item in MANIFESTO:
        if fase is not None and item.fase != fase:
            continue
        atendidas = tuple(s for s in item.sondas if sonda_atendida(s, raiz))
        faltando = tuple(s for s in item.sondas if s not in atendidas)
        saida.append(Resultado(item=item, atendidas=atendidas, faltando=faltando))
    return saida


_MARCA = re.compile(r"^## (S-\d{3}) · (.*?) (⬜ planejada|◐ parcial|✅ implementada)(?: \((\d{4}-\d{2}-\d{2})\))?\s*$")


def marcacoes_da_spec(raiz: Path = RAIZ) -> dict[str, str]:
    """`S-NN` -> a marcação escrita no cabeçalho da seção em `docs/SPEC_TEXTO.md`.

    É a **intenção declarada**, e serve para uma coisa só: ser comparada com o que as sondas
    acharam. Quem faz a comparação é `tests/test_text_status.py`.
    """
    texto = (raiz / SPEC).read_text(encoding="utf-8")
    marcado: dict[str, str] = {}
    for linha in texto.splitlines():
        achado = _MARCA.match(linha)
        if achado is not None:
            marcado[achado.group(1)] = achado.group(3).split(" ", 1)[1]
    return marcado


def resumo(resultados: list[Resultado]) -> dict[str, int]:
    """Contagem por estado, na ordem de `ESTADOS`."""
    return {estado: sum(1 for r in resultados if r.estado == estado) for estado in ESTADOS}
