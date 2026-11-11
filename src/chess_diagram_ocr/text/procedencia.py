"""De onde veio cada recorte de caractere: quem rotulou, e de que livro (S-201/S-203).

**A pasta não sabe.** Os 607.713 recortes de `training_data/` se chamam
`00001b60-272a-46f2-9dbf-044fe779e336.png` -- UUID puro, sem sidecar, sem índice, e com o `mtime`
inutilizável (70% carregam a data de uma migração em massa). Sem essa informação faltam **duas**
coisas ao mesmo tempo, e as duas são a mesma falta vista de ângulos diferentes:

- **a procedência** (S-201): um rótulo conferido por humano e um palpite de classificador não
  podem valer o mesmo. A avaliação de 2026-08-18 deste projeto abriu com quatro achados, e o
  primeiro é que a verdade de referência era a leitura do próprio modelo;
- **o livro** (S-203): fonte nova é livro novo, e o único teste que mede generalização de fonte é
  deixar um livro inteiro de fora. Sem livro, nenhuma acurácia desta base fala sobre fonte.

**Este módulo é o contrato do arquivo que responde as duas, escrito antes de o arquivo existir.**
Ele é o alvo do trabalho que só o `PyBoxEditor_Tkinter` pode fazer -- foi quem recortou --, e
está aqui para que o lado do treino esteja pronto no dia em que a resposta chegar. Definir o
formato depois seria convidar a duas migrações.

## O formato

`data/texto_procedencia.csv`, uma linha por recorte, cabeçalho obrigatório:

    uuid,livro,pagina,procedencia,rotulado_em
    00001b60-272a-46f2-9dbf-044fe779e336,Yusupov Build Up 1,212,humano,2026-02-16
    0000f4c1-8e2c-4b71-9a10-2b7f6d3e5a44,,,,

**Célula vazia é permitida e significa "não se sabe", que é diferente de a linha não existir.**
Um recorte com `livro` vazio entra no treino e fica fora de validação e de teste; um recorte que
o arquivo não menciona cai na mesma regra, pelo mesmo motivo. A diferença aparece no relatório:
a primeira é uma ausência **declarada**, a segunda é uma ausência **descoberta**.

## A regra que os três valores carregam

| valor | o que significa | onde pode entrar |
|---|---|---|
| `humano` | um humano olhou este recorte e disse qual é o caractere | treino, validação e **teste** |
| `modelo` | o rótulo é o palpite de um classificador | treino, e nunca validação nem teste |
| `desconhecida` | não há registro de quem rotulou | treino, e nunca validação nem teste |

**E um quarto, que não é valor novo e sim um `modelo` que diz qual** (S-762): `corrigido_de:<motor>@<sha do modelo>` é o par que a
pessoa corrigiu sobre a leitura de um motor. Entra no treino, com a versão do modelo que errou registrada, e nunca mede: quem corrige
vê a leitura, e a verdade ancorada no motor é o achado nº 1. `classe` o traduz para `modelo`, e é por isso que toda regra abaixo vale.

**E um quinto, que é um `humano` que diz como** (S-703): `transcricao:<passada>` é a verdade do scan-ouro, digitada às cegas de todo motor. É a
única que o scan-ouro aceita, porque o `humano` do bloco inteiro cobre as palavras que ninguém conferiu. `classe` o traduz para `humano`.

**Amostra sem procedência não é recusada -- ela é marcada.** Recusar 607 mil imagens porque
ninguém sabe de onde vieram desperdiça o ativo; deixá-las entrar no teste torna o número final
sem significado. É o mesmo meio-termo que este projeto já aplica a diagramas desde a S-19.

**E hoje o arquivo não existe**, então as 607.713 amostras são `desconhecida` e a regra acima
esvaziaria validação e teste. O que `cvoff-texto-train` faz nesse caso está escrito na seção
"Sem registro" do comando: ele mede assim mesmo e **grava a ressalva no relatório**, por extenso,
no lugar em que ninguém a lê por acidente.
"""

from __future__ import annotations

import csv
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import DATA_DIR, PROJECT_ROOT

logger = logging.getLogger(__name__)

HUMANO = "humano"
MODELO = "modelo"
DESCONHECIDA = "desconhecida"

VALORES = (HUMANO, MODELO, DESCONHECIDA)
"""Os três, e não mais. Um valor fora desta lista é erro de arquivo, não um quarto estado."""

CORRIGIDO_DE = "corrigido_de:"
"""O prefixo da correção humana sobre a leitura de um motor (S-762). Ver o cabeçalho."""

TRANSCRICAO = "transcricao:"
"""O prefixo da digitação às cegas do scan-ouro (S-703). Ver o cabeçalho."""

SEM_MODELO = "desconhecido"
"""O sha de quem foi lido antes de a página guardar o modelo: é o que o arquivo não sabe."""


def corrigido_de(motor: str, modelo: str = "") -> str:
    """`corrigido_de:glifo@ab12...`, a procedência de um par corrigido."""
    return f"{CORRIGIDO_DE}{motor}@{modelo or SEM_MODELO}"


def e_corrigido(valor: str) -> bool:
    return valor.startswith(CORRIGIDO_DE) and "@" in valor


def transcricao(passada: int) -> str:
    """`transcricao:1`, a procedência de uma folha digitada às cegas na passada dada."""
    return f"{TRANSCRICAO}{int(passada)}"


def e_transcricao(valor: str) -> bool:
    return valor.startswith(TRANSCRICAO) and valor[len(TRANSCRICAO):].isdigit()


def classe(valor: str) -> str:
    """Um dos três `VALORES`. O corrigido é rótulo ancorado num motor, e vale o que `modelo` vale: treino, e nunca medida.
    A transcrição é a mão sem leitura por trás, e vale o que `humano` vale."""
    if e_transcricao(valor):
        return HUMANO
    return MODELO if e_corrigido(valor) else valor


class VerdadeContaminada(ValueError):
    """Pediram para medir com um rótulo que não é verdade independente. Levanta: medir com ele não dá um número pior, dá um número falso."""


def exigir_verdade(valor: str, *, onde: str) -> None:
    """A porta de todo split de medida: o scan-ouro da S-703, o teste de caractere, e qualquer outro que venha."""
    if classe(valor) != HUMANO:
        raise VerdadeContaminada(f"{onde}: procedência {valor!r} não mede nada. Só a conferida por humano, sem leitura por trás, mede.")


def exigir_transcricao(valor: str, *, onde: str) -> None:
    """A porta do scan-ouro, mais estreita que `exigir_verdade`: o `humano` do bloco inteiro também não entra (S-703)."""
    exigir_verdade(valor, onde=onde)
    if not e_transcricao(valor):
        raise VerdadeContaminada(f"{onde}: procedência {valor!r} não é digitação às cegas. O scan-ouro só aceita `{TRANSCRICAO}<passada>`.")


CODIGO = {DESCONHECIDA: 0, MODELO: 1, HUMANO: 2}
"""Procedência -> inteiro, para caber num `int8` por amostra em vez de uma lista de strings.

A ordem é a da confiança que cada uma merece, e ela não é decorativa: `código >= CODIGO[HUMANO]`
é o teste de "pode entrar na medição", e escrevê-lo como comparação em vez de conjunto deixa a
regra legível onde ela é aplicada."""

NOME = {valor: chave for chave, valor in CODIGO.items()}

CAMINHO_PADRAO = DATA_DIR / "texto_procedencia.csv"
COLUNAS = ("uuid", "livro", "pagina", "procedencia", "rotulado_em")


class ArquivoInvalido(ValueError):
    """O CSV existe e não é o contrato. Levanta em vez de tratar tudo como desconhecido.

    **Ler um arquivo malformado como "nenhuma procedência" seria o pior dos dois mundos**: o
    trabalho de recuperar a origem estaria feito, o número sairia como se não estivesse, e nada
    diria a diferença.
    """


@dataclass(frozen=True)
class Registro:
    """O que o arquivo diz sobre um recorte. Campo vazio é "não se sabe", e é declarado."""

    livro: str = ""
    pagina: int | None = None
    procedencia: str = DESCONHECIDA
    rotulado_em: str = ""

    @property
    def mede(self) -> bool:
        """Esta amostra pode entrar em validação e teste? Só a conferida por humano pode."""
        return classe(self.procedencia) == HUMANO

    @property
    def tem_livro(self) -> bool:
        return bool(self.livro.strip())


VAZIO: dict[str, Registro] = {}
"""O registro de quem não tem arquivo nenhum. Nomeado para que o caminho sem dados seja visível
em quem chama, em vez de um `{}` solto que se lê como esquecimento."""


def ler(caminho: Path | str | None = None) -> dict[str, Registro]:
    """`uuid -> Registro`, ou `{}` quando o arquivo não existe. **Ausente não é erro.**

    Ausente é o estado de hoje e o de todo clone: o arquivo depende de um trabalho no projeto de
    origem que ainda não aconteceu. Malformado, sim, é erro -- ver `ArquivoInvalido`.

    O `uuid` é a chave, e é o **nome do arquivo sem a extensão**: é assim que o recorte é
    encontrado, e é a única coisa que a pasta e o arquivo têm em comum.
    """
    alvo = Path(caminho) if caminho is not None else CAMINHO_PADRAO
    if not alvo.exists():
        logger.info("Sem registro de procedência em %s: toda amostra entra como desconhecida.", alvo)
        return {}

    with open(alvo, encoding="utf-8", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)
        faltando = [coluna for coluna in COLUNAS if coluna not in (leitor.fieldnames or [])]
        if faltando:
            raise ArquivoInvalido(f"{alvo} não tem as colunas {', '.join(faltando)}.")

        registro: dict[str, Registro] = {}
        for numero, linha in enumerate(leitor, start=2):
            uuid = (linha.get("uuid") or "").strip()
            if not uuid:
                raise ArquivoInvalido(f"{alvo}, linha {numero}: uuid vazio.")
            valor = (linha.get("procedencia") or "").strip().lower() or DESCONHECIDA
            if valor not in VALORES and not e_corrigido(valor) and not e_transcricao(valor):
                raise ArquivoInvalido(
                    f"{alvo}, linha {numero}: procedência {valor!r} não é uma de {', '.join(VALORES)}."
                )
            pagina_bruta = (linha.get("pagina") or "").strip()
            registro[uuid] = Registro(
                livro=(linha.get("livro") or "").strip(),
                pagina=int(pagina_bruta) if pagina_bruta.isdigit() else None,
                procedencia=valor,
                rotulado_em=(linha.get("rotulado_em") or "").strip(),
            )

    logger.info("Procedência lida de %s: %d recorte(s) registrado(s).", alvo, len(registro))
    return registro


def resumo(registro: dict[str, Registro]) -> str:
    """Uma linha em pt-BR sobre o que o arquivo trouxe. Para o log e para a tela."""
    if not registro:
        return "sem registro de procedência: toda amostra entra como desconhecida"
    por_valor = {valor: sum(1 for r in registro.values() if classe(r.procedencia) == valor) for valor in VALORES}
    livros = len({r.livro for r in registro.values() if r.tem_livro})
    return (
        f"{len(registro):,} recorte(s) registrado(s): "
        f"{por_valor[HUMANO]:,} humano, {por_valor[MODELO]:,} modelo, "
        f"{por_valor[DESCONHECIDA]:,} desconhecida; {livros} livro(s)"
    ).replace(",", ".")


CAMINHO_DO_VAZAMENTO = PROJECT_ROOT / "docs" / "metrics" / "texto_vazamento.json"
"""Onde `cvoff-texto-train` grava o relatório de vazamento, e onde o `cvoff-audit` o lê."""


def violacoes_do_split(relatorio: Mapping[str, Any]) -> list[str]:
    """O que há de errado no último split da base de caractere, em pt-BR. Vazio é aprovado.

    **É a metade da S-201 que o `cvoff-audit` cobra**, e ela precisa de um relatório porque o
    split não existe em disco: ele é função pura da semente e é refeito a cada corrida, de
    propósito (ver `dataset.gravar_cache`). O que fica gravado é o que ele produziu.

    As quatro violações, e as duas primeiras não dependem de procedência nenhuma:

    - grupo de cópia exata em dois lados -- o modelo mediria a própria memória;
    - livro em dois lados -- desfaz o único teste que mede generalização de fonte;
    - rótulo de **modelo** medindo o modelo -- é o achado nº 1 da avaliação de 2026-08-18 deste
      projeto, e ele não tem atenuante;
    - rótulo **desconhecido** medindo o modelo **quando há registro no disco**. Sem registro isso
      é a base inteira, e reprovar aqui seria reprovar o único número que existe -- a ressalva
      vai no relatório, que é onde ela é lida junto com o número.
    """
    achados: list[str] = []
    grupos = int(relatorio.get("grupos_em_dois_lados", 0) or 0)
    livros = int(relatorio.get("livros_em_dois_lados", 0) or 0)
    por_lado = relatorio.get("procedencia_por_lado") or {}
    teste = por_lado.get("teste") or {}
    tem_registro = not str(relatorio.get("registro_de_procedencia", "")).startswith("sem registro")
    permitido = bool(relatorio.get("desconhecida_no_teste_permitida"))

    if grupos:
        achados.append(f"{grupos} grupo(s) de cópia exata em mais de um lado do split de caractere")
    if livros:
        achados.append(f"{livros} livro(s) em mais de um lado do split de caractere")
    if int(teste.get(MODELO, 0) or 0):
        achados.append(
            f"{int(teste[MODELO])} amostra(s) com rótulo de modelo no split de teste de caractere "
            "-- a verdade de referência não pode ser a leitura de um classificador (S-201)"
        )
    desconhecidas = int(teste.get(DESCONHECIDA, 0) or 0)
    if desconhecidas and tem_registro and not permitido:
        achados.append(
            f"{desconhecidas} amostra(s) sem procedência no split de teste de caractere, e há "
            "registro no disco -- use --desconhecida-no-teste se isso for deliberado (S-201)"
        )
    return achados


__all__ = [
    "CAMINHO_DO_VAZAMENTO",
    "CAMINHO_PADRAO",
    "CODIGO",
    "COLUNAS",
    "CORRIGIDO_DE",
    "DESCONHECIDA",
    "HUMANO",
    "MODELO",
    "NOME",
    "VALORES",
    "VAZIO",
    "ArquivoInvalido",
    "Registro",
    "VerdadeContaminada",
    "classe",
    "corrigido_de",
    "e_corrigido",
    "exigir_verdade",
    "ler",
    "resumo",
    "violacoes_do_split",
]


def acrescentar(
    novos: Mapping[str, Registro],
    caminho: Path | str | None = None,
) -> Path:
    """Junta registros ao CSV, criando-o com cabeçalho quando ele ainda não existe (S-214).

    **Este módulo só tinha `ler`, e é por isso que a S-201 estava parada.** O arquivo dependia de
    um trabalho no projeto de origem para os 608 mil recortes que já existem -- e continua
    dependendo, porque o nome deles é UUID puro e a origem se perdeu. O que muda aqui é o
    **daqui para a frente**: o recorte que a coleta da S-214 promove entra com livro, página e
    `humano` no mesmo arquivo, porque quem o rotulou moveu a pasta com a mão.

    **Registro repetido é atualizado, e não duplicado.** O arquivo é lido antes, fundido, e
    reescrito inteiro: um CSV com dois `uuid` iguais e procedências diferentes não tem resposta,
    e `ler` devolveria o último em silêncio. O custo é reler um arquivo que a base inteira não
    passa de 608 mil linhas.
    """
    alvo = Path(caminho) if caminho is not None else CAMINHO_PADRAO
    juntos = dict(ler(alvo)) if alvo.exists() else {}
    juntos.update(novos)

    alvo.parent.mkdir(parents=True, exist_ok=True)
    linhas = [",".join(COLUNAS)]
    for uuid in sorted(juntos):
        r = juntos[uuid]
        pagina = "" if r.pagina is None else str(r.pagina)
        linhas.append(",".join((uuid, _sem_virgula(r.livro), pagina, r.procedencia, r.rotulado_em)))

    from ..atomic_io import atomic_write_text

    atomic_write_text(alvo, "\n".join(linhas) + "\n")
    logger.info("Procedência: %d registro(s) em %s (%d novo(s)).", len(juntos), alvo, len(novos))
    return alvo


def _sem_virgula(valor: str) -> str:
    """O nome do livro sem vírgula, porque este CSV não cita campo.

    **Um livro do acervo tem vírgula no nome** (`1001_Winning_Chess_Sacrifices_and_Combinations,_Fred...`),
    e escrito cru ele partiria a linha em seis campos -- `ler` leria a página como procedência e
    levantaria `ArquivoInvalido` sobre um arquivo que este módulo mesmo escreveu. Trocar por espaço
    perde menos que citar: a chave é o `uuid`, e o livro é para o humano ler."""
    return valor.replace(",", " ").strip()
