"""A correção humana como dado, sem contaminar nada (S-762).

**A correção é registro, e não rótulo** (`text/correcao.py`), e continua sendo: nada aqui escreve em `training_data/`. Mas ela
é o dado mais barato que o programa produz, e estava sem caminho. Há duas portas, e a diferença entre elas é o item:

- **para a medição, fechada.** Texto corrigido sobre a saída de um motor herda o motor: quem corrige vê a leitura e só mexe no
  que nota, e o resto do bloco fica ancorado nela. A S-703 proíbe verdade assim. `exigir_documento_cego` recusa o `.cvtxt`
  corrigido como referência, e `procedencia.exigir_verdade` recusa o carimbo `corrigido_de:` em qualquer split de medida.
- **para o treino, pela quarentena da S-214**, e só **o par palavra a palavra que a pessoa tocou**. O carimbo `humano` de
  `correcao.com_procedencia_humana` vale para o bloco inteiro e serve à tela, que deixa de pintar o que a pessoa conferiu; ele não é
  lido aqui. Quem diz o que a mão tocou é o alinhamento entre o que o motor leu e o que ficou (`pares_tocados`).

**O que chega à quarentena são caracteres**, porque é o que ela guarda: só o par de mesmo tamanho, só as letras que mudaram, e só
quando as caixas da linha casam uma a uma com as letras que o motor leu nela (`recortes_do_par`). O resto conta como `sem_recorte`,
e não se adivinha. Cada recorte leva a procedência `corrigido_de:<motor>@<sha do modelo>`, que `coleta.promover` grava no registro
no lugar de `humano`: entra no treino, e nunca mede.

**O livro do teste nunca entra**, nem o que o manifesto tira do treino: `livro_recusado`. Livro sem identidade também não: sem ela
não há como saber que não é do teste.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import numpy as np

from . import coleta as _coleta
from . import correcao as _correcao
from . import ouro as _ouro
from . import procedencia as _procedencia
from .boxes import Caixa
from .caderno import identidade_de
from .classes import NomeDePastaInvalido, char_to_folder
from .pagina import BlocoDeTexto, LinhaLida, PaginaLida, Procedencia
from .rico import DocumentoRico

MOTORES_DE_LEITURA: frozenset[str] = frozenset({"glifo", "rapidocr", "tesseract"})
"""De quem se pode dizer que errou. `camada` é o que o editor escreveu, e `humano` já é a mão."""


class FolhaAncorada(ValueError):
    """Esta folha foi escrita sobre a leitura de um motor, e não serve de verdade (S-703)."""


@dataclass(frozen=True)
class ParTocado:
    """Uma palavra que o motor leu de um jeito e a pessoa deixou de outro."""

    bloco: int
    palavra: int
    """A posição da palavra no bloco, na leitura do motor."""
    antes: str
    depois: str
    motor: Procedencia
    modelo: str
    """O sha do modelo que gerou o texto, de `PaginaLida.modelo`. Vazio é o `.cvtxt` de antes da S-762."""

    @property
    def procedencia(self) -> str:
        return _procedencia.corrigido_de(self.motor, self.modelo)


def pares_tocados(doc: DocumentoRico) -> tuple[ParTocado, ...]:
    """Os pares palavra a palavra. **O alinhamento é por palavra**, e o que ninguém tocou não aparece em par nenhum.

    Só a troca de uma palavra por uma: `ofthe` -> `of the` e a palavra acrescentada não têm par que o treino use.
    """
    if doc.origem is None:
        return ()
    atual = _correcao.texto_por_bloco(doc)
    modelo = doc.origem.modelo
    achados: list[ParTocado] = []
    for bloco, (antes, motor) in sorted(_correcao._blocos_comparaveis(doc).items()):
        if motor not in MOTORES_DE_LEITURA or atual[bloco] == antes:
            continue
        lidas, ficaram = antes.split(), atual[bloco].split()
        for op, i1, i2, j1, j2 in SequenceMatcher(None, lidas, ficaram, autojunk=False).get_opcodes():
            if op != "replace" or i2 - i1 != j2 - j1:
                continue
            achados.extend(
                ParTocado(bloco, i1 + k, lidas[i1 + k], ficaram[j1 + k], motor, modelo) for k in range(i2 - i1)
            )
    return tuple(achados)


def exigir_documento_cego(doc: DocumentoRico, *, onde: str) -> None:
    """Levanta se o documento tem leitura de motor por trás. É a porta da verdade do scan-ouro e de qualquer teste.

    **Corrigido ou não**: o texto que veio de um motor e ninguém tocou é do motor, e o que foi tocado foi escrito olhando para ele.
    """
    if doc.origem is None:
        return
    motores = sorted(set(doc.origem.procedencias()) & MOTORES_DE_LEITURA)
    if motores:
        raise FolhaAncorada(f"{onde}: a folha foi escrita sobre a leitura de {', '.join(motores)}, e a verdade tem de ser cega.")


def livro_recusado(pdf: str | Path, manifesto: _ouro.Manifesto | None = None) -> str:
    """Por que este livro não vai à quarentena, ou vazio se pode ir. Só compara identidades: nenhuma folha é aberta."""
    identidade = identidade_de(pdf)
    if identidade is None:
        return "sem identidade: não há como saber se o livro é do teste"
    for livro in (manifesto if manifesto is not None else _ouro.carregar()).livros:
        if livro.identidade != identidade:
            continue
        if livro.split == _ouro.TESTE:
            return "livro do teste"
        if livro.fora_do_treino:
            return "o manifesto o tira do treino"
    return ""


def _linhas_do_bloco(pagina: PaginaLida, bloco: int) -> Sequence[LinhaLida] | None:
    alvo = pagina.blocos[bloco]
    return alvo.linhas if isinstance(alvo, BlocoDeTexto) and alvo.linhas else None


def recortes_do_par(
    par: ParTocado,
    pagina: PaginaLida,
    cinza: np.ndarray,
    caixas: Sequence[Caixa],
    *,
    escala_px: float,
) -> list[_coleta.Recorte]:
    """As letras que mudaram, recortadas da folha. Vazio quando não há como apontar a tinta sem adivinhar.

    **As caixas da linha têm de casar uma a uma com as letras dela.** Ligadura, letra colada e pingo solto fazem a conta não fechar, e
    aí o par fica sem recorte: um recorte da letra vizinha com o rótulo desta é o defeito das 127 amostras da S-180.
    """
    import cv2

    if len(par.antes) != len(par.depois):
        return []
    linhas = _linhas_do_bloco(pagina, par.bloco)
    if linhas is None:
        return []
    restante = par.palavra
    linha: LinhaLida | None = None
    for candidata in linhas:
        n = len(candidata.texto.split())
        if restante < n:
            linha = candidata
            break
        restante -= n
    if linha is None or linha.texto.split()[restante] != par.antes:
        # A hifenizada juntou duas linhas numa palavra, e a conta por linha não vale mais.
        return []
    x0, y0, x1, y1 = (v * escala_px for v in linha.bbox)
    da_linha = sorted(
        (c for c in caixas if x0 <= (c.x1 + c.x2) / 2 <= x1 and y0 <= (c.y1 + c.y2) / 2 <= y1), key=lambda c: c.x1
    )
    tokens = linha.texto.split()
    if len(da_linha) != sum(len(t) for t in tokens):
        return []
    inicio = sum(len(t) for t in tokens[:restante])
    saida: list[_coleta.Recorte] = []
    for k, (lida, certa) in enumerate(zip(par.antes, par.depois, strict=True)):
        if lida == certa:
            continue
        try:
            char_to_folder(certa)
        except (NomeDePastaInvalido, ValueError):
            continue
        imagem = da_linha[inicio + k].recortar(cinza)
        if imagem.size:
            saida.append(
                _coleta.Recorte(
                    cv2.resize(imagem, (_coleta.LADO, _coleta.LADO)),
                    certa,
                    0.0,
                    livro=Path(pagina.documento).stem,
                    pagina=pagina.pagina,
                    procedencia=par.procedencia,
                    antes=par.antes,
                    depois=par.depois,
                )
            )
    return saida


@dataclass
class EnvioAQuarentena:
    """O que aconteceu com as correções de uma folha."""

    pares: int = 0
    recortes: int = 0
    sem_recorte: int = 0
    recusado: str = ""
    procedencias: dict[str, int] = field(default_factory=dict)

    def juntar(self, outro: EnvioAQuarentena) -> None:
        self.pares += outro.pares
        self.recortes += outro.recortes
        self.sem_recorte += outro.sem_recorte
        for chave, n in outro.procedencias.items():
            self.procedencias[chave] = self.procedencias.get(chave, 0) + n

    def para_json(self) -> dict[str, Any]:
        return {
            "pares": self.pares,
            "recortes": self.recortes,
            "sem_recorte": self.sem_recorte,
            "recusado": self.recusado,
            "procedencias": dict(sorted(self.procedencias.items())),
        }


def preparar(
    doc: DocumentoRico,
    pdf: str | Path,
    imagem_rgb: np.ndarray,
    *,
    dpi: int,
    manifesto: _ouro.Manifesto | None = None,
) -> tuple[list[_coleta.Recorte], EnvioAQuarentena]:
    """Os recortes das correções da folha, sem gravar nada. O livro do teste sai daqui sem nada."""
    envio = EnvioAQuarentena()
    pares = pares_tocados(doc)
    envio.pares = len(pares)
    if not pares or doc.origem is None:
        return ([], envio)
    envio.recusado = livro_recusado(pdf, manifesto)
    if envio.recusado:
        envio.sem_recorte = len(pares)
        return ([], envio)

    from . import leitor as _leitor

    cinza, _binaria, _escala, caixas, _regioes = _leitor.segmentar(imagem_rgb, dpi=dpi)
    recortes: list[_coleta.Recorte] = []
    for par in pares:
        destes = recortes_do_par(par, doc.origem, cinza, caixas, escala_px=dpi / 72.0)
        if not destes:
            envio.sem_recorte += 1
        recortes.extend(destes)
    envio.recortes = len(recortes)
    for recorte in recortes:
        envio.procedencias[recorte.procedencia] = envio.procedencias.get(recorte.procedencia, 0) + 1
    return (recortes, envio)


def enviar(recortes: Iterable[_coleta.Recorte], destino: Path | str = _coleta.PASTA_PADRAO) -> _coleta.Relatorio:
    """Grava na quarentena. Sem teto: o que a mão tocou é pouco, e cada recorte foi pago por alguém."""
    return _coleta.coletar(recortes, destino, teto=10**9)


__all__ = [
    "MOTORES_DE_LEITURA",
    "EnvioAQuarentena",
    "FolhaAncorada",
    "ParTocado",
    "enviar",
    "exigir_documento_cego",
    "livro_recusado",
    "pares_tocados",
    "preparar",
    "recortes_do_par",
]
