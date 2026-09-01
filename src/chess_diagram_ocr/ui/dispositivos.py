"""Em que dispositivo cada um dos dois modelos torch está rodando (S-182).

**Desde 2026-08-23 a janela tem dois.** O classificador de peças (8,8 MB) e o de caracteres
(2,6 MB) passam a conviver no mesmo processo, e cada um escolhe o dispositivo por conta própria:
`inference.load_model` e `text.modelo._escolher_device` fazem a mesma pergunta ao torch em dois
lugares diferentes. É o risco 5 do `ROADMAP_TEXTO`, e o que ele prevê é o defeito que a S-30 já
mediu uma vez -- uma máquina com placa mas com o torch `+cpu` instalado roda na CPU **em
silêncio**, e a diferença entre 7,5 min e ~45 s por época era invisível. Com dois modelos o
silêncio fica pior, porque eles podem discordar entre si na mesma sessão.

**Este módulo é a cola, e ela mora aqui e não na janela.** O rodapé recebe descrições
prontas de propósito -- é o que faz `compor` ser afirmável sem abrir janela -- e `app_tkinter.py`
tem catraca de tamanho desde a S-31. O que sobra é um lugar próprio para a única pergunta que
precisa do serviço, da configuração e do rodapé ao mesmo tempo.

**Nada aqui levanta quando falta alguma coisa.** Um leitor de legenda que não é o `glifo` não
tem classificador, e perguntar por um é o caso normal: três dos quatro motores da S-42 não
entendem a pergunta. A resposta é `None`, e quem diz **por que** não há um é a configuração.
"""

from __future__ import annotations

from typing import Any

from . import estado_do_rodape as rodape

__all__ = ["descricao_do_classificador_de_caracteres", "dispositivos_da_janela"]


def descricao_do_classificador_de_caracteres() -> str | None:
    """A descrição do dispositivo do classificador de caracteres, ou `None` quando não há um.

    Pergunta ao cache de `text.modelo` e **não carrega nada**: quem decide pagar os 2,6 MB é
    quem vai classificar. Um leitor de legenda que não seja o `glifo` nunca põe nada lá, e é por
    isso que `None` é o caso normal e não uma falha -- três dos quatro motores da S-42 não têm
    classificador nenhum.

    **Não passa pelo `CaptionReader` de propósito.** Ir do leitor até o classificador exigiria
    uma porta nova em `ocr_caption.py`, que está no fecho de importação de `cvoff-field`: mexer
    ali invalidaria o digest dos relatórios de campo (S-219) por causa de uma linha de rodapé.
    O `text/` é podado desse digest, e é onde esta pergunta já morava.
    """
    # Tarde, e não no topo: `text.modelo` alcança `torch` pelo caminho de carga, e este módulo é
    # importado pela janela antes de qualquer modelo existir.
    from ..text.modelo import dispositivo_em_uso  # noqa: PLC0415 - ver acima

    device = dispositivo_em_uso()
    if device is None:
        return None

    from ..inference import describe_device  # noqa: PLC0415 - idem

    return describe_device(device)


def dispositivos_da_janela(servico: Any, ocr: Any) -> rodape.Dispositivos:
    """O que a zona de dispositivos do rodapé mostra, lida do serviço e da configuração.

    **Relida a cada tique porque nenhum dos dois modelos avisa quando muda**: o de peças carrega
    na primeira leitura da sessão, e o de caracteres é trocado quando um retreino reescreve o
    `.pt` -- `text.modelo._CACHE` tem o `mtime` na chave justamente por isso.

    Quando não há classificador de caracteres, quem sabe **por quê** é a configuração: um motivo
    não vazio é "os pesos não estão no disco", e vazio é "o motor escolhido é outro, ou o OCR de
    legenda está desligado". As duas são normais, e dizê-las com a mesma palavra mandaria metade
    das pessoas procurar um arquivo que já está lá.
    """
    motivo = ocr.glyph_disabled_reason()
    return rodape.Dispositivos(
        pecas=servico.device_label if servico.device else None,
        caracteres=descricao_do_classificador_de_caracteres(),
        motivo=motivo,
        ausencia=rodape.SEM_PESOS if motivo else rodape.DESLIGADO,
    )
