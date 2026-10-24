"""O que a janela *Configurações…* mostra, declarado uma vez e sem Qt.

**Por que uma tabela e não widgets escritos à mão.** O programa tinha preferências que
ninguém conseguia mudar pela janela: `data/settings.json` só era lido, e o número de épocas
do treino era uma constante em `qt/janela.py`. Quem pedia "quantas épocas quero treinar"
precisava editar um arquivo que a interface nunca gravava. A resposta não é um formulário
com sete spinboxes: é uma **declaração** de cada preferência -- seção, nome, tipo, faixa,
ajuda -- que o diálogo (`qt/dialogo_de_configuracoes.py`) transforma em controle e que o
teste confere contra `settings.Settings` sem abrir tela: toda entrada aqui aponta para um
campo que existe, e todo campo simples de `Settings` aparece aqui ou está declarado como
fora da janela (`FORA_DA_JANELA`, com o motivo).

Cada `Campo` nomeia `secao.campo` de `Settings` -- `training.epochs` é
`settings.training.epochs`. O diálogo lê e grava por `dataclasses.replace`, então uma
preferência nova custa uma linha nesta tabela e um campo no dataclass, e nada mais.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chess_diagram_ocr import settings as preferencias

__all__ = ["ABAS", "CAMPOS", "FORA_DA_JANELA", "Campo", "dpi", "ler", "max_boards", "reconhecimento", "trocar"]

INTEIRO = "inteiro"
DECIMAL = "decimal"
INTERRUPTOR = "interruptor"
TEXTO = "texto"
CAMINHO = "caminho"
ESCOLHA = "escolha"
LISTA = "lista"


@dataclass(frozen=True)
class Campo:
    chave: str
    """`secao.campo`, nos nomes de `settings.Settings`."""
    rotulo: str
    tipo: str
    ajuda: str = ""
    """Uma frase: o que muda quando o número muda. Vira a dica do controle."""
    minimo: float | None = None
    maximo: float | None = None
    passo: float | None = None
    opcoes: tuple[str, ...] = ()
    decimais: int = 4

    @property
    def secao(self) -> str:
        return self.chave.split(".", 1)[0]

    @property
    def campo(self) -> str:
        return self.chave.split(".", 1)[1]


ABAS: tuple[tuple[str, str], ...] = (
    ("training", "Treino"),
    ("recognition", "Reconhecimento"),
    ("ocr", "OCR"),
    ("engine", "Motor de análise"),
    ("remote_fen", "Segunda opinião"),
)
"""`(seção, título da aba)`, na ordem em que aparecem. A seção `local_reader` entra na aba
da segunda opinião: as duas são a mesma pergunta (quem mais lê o diagrama) com respostas
que diferem no que importa -- uma sai da máquina, a outra não."""

CAMPOS: tuple[Campo, ...] = (
    # --- treino: o que custa dezenas de minutos por clique
    Campo("training.epochs", "Épocas do classificador de peças", INTEIRO,
          "Quantas passagens pelo dataset o treino do modelo de peças faz ao clicar em "
          "Treinar. Mais épocas: mais tempo e, até certo ponto, um modelo melhor -- o "
          "treino só grava por cima quando a validação melhora.", 1, 200, 1),
    Campo("training.batch_size", "Tamanho do lote", INTEIRO,
          "Casas por passo do treino. Maior é mais rápido e usa mais memória.", 1, 512, 8),
    Campo("training.lr", "Taxa de aprendizado", DECIMAL,
          "Passo do otimizador. 0,001 é o padrão medido; dez vezes maior costuma divergir.",
          1e-6, 1.0, 1e-4, decimais=6),
    Campo("training.ocr_iterations", "Iterações do ajuste fino do OCR", INTEIRO,
          "Quantas iterações o Tesseract treina por livro (aba Rotulagem, Treinar…). "
          "2.000 leva ~16 min nesta máquina.", 100, 50000, 100),
    Campo("training.ocr_learning_rate", "Taxa do ajuste fino do OCR", DECIMAL,
          "Passo do treino do Tesseract.", 1e-6, 1.0, 1e-4, decimais=6),
    Campo("training.ocr_negatives", "Negativos no ajuste fino do OCR", INTEIRO,
          "Linhas de prosa do livro re-renderizadas sob ruído, com a mesma verdade, para o "
          "modelo não ver figurinas onde há mancha. 0 desliga.", 0, 5000, 20),
    # --- reconhecimento
    Campo("recognition.dpi", "Resolução da página (DPI)", INTEIRO,
          "Com que resolução a página é rasterizada antes de procurar diagramas. 220 é o "
          "que os relatórios de campo medem; subir ajuda em scans fracos e custa tempo.",
          72, 600, 10),
    Campo("recognition.max_boards", "Diagramas por página, no máximo", INTEIRO,
          "Quantos diagramas o detector procura numa página.", 1, 64, 1),
    # --- OCR das páginas sem camada de texto
    Campo("ocr.enabled", "Ler o texto das páginas sem camada de texto", INTERRUPTOR,
          "Desligado, o programa só usa a camada de texto do PDF; ligado, roda o motor de "
          "OCR nas páginas que não a têm."),
    Campo("ocr.engine", "Motor de OCR", ESCOLHA,
          "rapidocr não baixa nada; easyocr baixa ~100 MB no primeiro uso; glifo é o "
          "modelo de casa (models/char_classifier.pt).",
          opcoes=("rapidocr", "easyocr", "tesseract", "glifo")),
    Campo("ocr.languages", "Idiomas", LISTA,
          "Separados por vírgula: pt, en, es, de."),
    Campo("ocr.glyph_model", "Modelo de glifos", CAMINHO,
          "Checkpoint do motor 'glifo' (vazio: o de fábrica, models/char_classifier.pt)."),
    # --- motor UCI
    Campo("engine.path", "Executável do motor UCI", CAMINHO,
          "Vazio: o programa procura no PATH. A seção de análise só aparece com um motor."),
    Campo("engine.movetime_ms", "Tempo por lance (ms)", INTEIRO,
          "Quanto o motor pensa em cada posição.", 50, 60000, 50),
    Campo("engine.threads", "Threads do motor", INTEIRO, "", 1, 64, 1),
    # --- segunda opinião
    Campo("local_reader.enabled", "Segunda opinião local", INTERRUPTOR,
          "Um segundo modelo, offline (tsoj/Chess_diagram_to_FEN), lê o diagrama. "
          "232 MiB de pesos e ~7 s na primeira leitura."),
    Campo("local_reader.path", "Pasta do leitor local", CAMINHO,
          "Clone de tsoj/Chess_diagram_to_FEN com os pesos baixados."),
    Campo("remote_fen.enabled", "Segunda opinião remota", INTERRUPTOR,
          "Envia a IMAGEM do diagrama para o serviço abaixo. Desligado por padrão; o programa "
          "pede confirmação nomeando o host antes do primeiro envio."),
    Campo("remote_fen.endpoint", "Endereço do serviço remoto", TEXTO,
          "https://… — sem endereço o recurso não existe, de propósito."),
    Campo("remote_fen.timeout", "Tempo limite (s)", DECIMAL, "", 1.0, 300.0, 1.0, decimais=1),
)

FORA_DA_JANELA: dict[str, str] = {
    "remote_fen.acknowledged_host": "é o consentimento gravado ao aceitar o aviso, não uma escolha",
}
"""Campos de `Settings` que a janela não mostra, com o motivo. O teste cobra que todo campo
esteja aqui ou em `CAMPOS` -- uma preferência nova sem lugar declarado é o defeito de origem."""


def ler(configuracao: preferencias.Settings, campo: Campo) -> Any:
    return getattr(getattr(configuracao, campo.secao), campo.campo)


def trocar(configuracao: preferencias.Settings, valores: dict[str, Any]) -> preferencias.Settings:
    """Um `Settings` novo com os valores da janela por cima, seção a seção."""
    por_secao: dict[str, dict[str, Any]] = {}
    for chave, valor in valores.items():
        secao, campo = chave.split(".", 1)
        por_secao.setdefault(secao, {})[campo] = valor
    novo = configuracao
    for secao, campos in por_secao.items():
        atual = getattr(novo, secao)
        novo = dataclasses.replace(novo, **{secao: dataclasses.replace(atual, **campos)})
    return novo


_RECONHECIMENTO: tuple[tuple[int, int] | None, preferencias.RecognitionSettings] | None = None


def reconhecimento(caminho: Path = preferencias.DEFAULT_SETTINGS_PATH) -> preferencias.RecognitionSettings:
    """A seção de reconhecimento, relida só quando `settings.json` muda em disco.

    `qt/janela.py` pergunta o DPI e o teto de diagramas a cada página lida e a cada
    sobreposição desenhada; ler e validar o JSON doze vezes por página seria custo puro. A
    chave `(tamanho, mtime)` é a mesma de `qt/campo._ler`: gravar pela janela de configurações
    muda os dois valores, e a próxima página já sai com o número novo.
    """
    global _RECONHECIMENTO
    try:
        estado = Path(caminho).stat()
        chave: tuple[int, int] | None = (estado.st_size, estado.st_mtime_ns)
    except OSError:
        chave = None
    if _RECONHECIMENTO is not None and chave is not None and _RECONHECIMENTO[0] == chave:
        return _RECONHECIMENTO[1]
    lido = preferencias.load_settings(Path(caminho)).recognition
    _RECONHECIMENTO = (chave, lido)
    return lido


def dpi() -> int:
    return reconhecimento().dpi


def max_boards() -> int:
    return reconhecimento().max_boards
