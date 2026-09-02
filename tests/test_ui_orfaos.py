"""De cada decisão pura de `ui/`, quem a chama? (S-511)

**A conta que faltava.** O catálogo pergunta se uma ação tem *dono* e se o dono é *chamável* --
`lambda: None` passa nas duas. Nada perguntava se um módulo puro de `ui/` ainda tem **importador**,
e módulo órfão não quebra teste nenhum: o teste dele continua verde medindo a decisão sozinha.

Foi assim que sete decisões ficaram sem chamador no corte do Tk e só voltaram um mês depois
(`adda88f`). As S-507 a S-510 são a oitava à décima primeira, e as quatro moram no mesmo arquivo:
`ui/desenho_do_tabuleiro.py`, que tinha **doze apelidos de cor** existindo para um `tk.Canvas` que
já não existe. A instância muda; o mecanismo não.

**O que esta guarda é e o que ela não é.** Ela não é "conserte os órfãos". É tornar a pergunta
fazível e travar o número. `desenho_do_tabuleiro.py` -- o módulo que este item triou -- não pode
ter nenhum, salvo exceção com motivo escrito; o resto do pacote entra numa catraca que **desce
quando alguém tria um e não sobe**.

**Por que `ast` e não `grep`.** Um nome citado num docstring conta como uso para o `grep`, e é o
caso mais comum de todos neste projeto -- os módulos se descrevem uns aos outros em prosa. A
varredura por identificador conta só o que o código **usa**.

**O que a guarda mede, e o que ela deliberadamente não mede.** Ela pergunta se o **produto**
(`src/`) chama o nome, e não se algum teste o toca. Medido em 2026-09-01, a diferença é grande:
dos 125 nomes que a busca de texto não achava em `src/`, 48 eram tocados por algum teste e 77 não
eram tocados por nada. Um nome que só o próprio teste usa continua sendo uma decisão sem cliente --
é exatamente o estado que deixou as sete passarem despercebidas.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr"
UI = RAIZ / "ui"

SEM_CHAMADOR: dict[str, str] = {
    "estudo_lista.NIVEL_MAXIMO_DE_RECUO": (
        "quem o aplica é o próprio `Trecho.recuo`, no mesmo módulo, e o painel usa o resultado. "
        "Ele tinha chamador até a S-514, quando o recuo saiu do `<span>` e foi para o bloco: o "
        "desenho passou a ler `trecho.recuo`, que já vem saturado. Chamá-lo de fora agora seria "
        "repetir a saturação que a propriedade faz -- um chamador escrito para a guarda ficar "
        "verde, que é o `lambda: None` ao contrário."
    ),
    "desenho_do_tabuleiro.LARGURA_DO_CIRCULO": (
        "a casa marcada do padrão `[%csl]` ainda não é oferecida pela sala -- `_soltar_seta` "
        "recusa a seta de comprimento zero, que é o gesto que a marcaria. A espessura do anel "
        "fica declarada para quando o gesto existir, e não como número solto no widget."
    ),
}
"""`modulo.NOME -> motivo`, e o motivo não pode ser vazio.

**É um mapa, e não uma lista de perdão.** `test_a_excecao_declarada_ainda_e_orfa` exige que quem
está aqui continue **sem** chamador: um nome que ganhou um e ficou na lista reprova, senão a lista
vira o lugar onde a pergunta deixa de ser feita. É a mesma forma do `RENUMERADOS` de
`tests/test_docs.py`.
"""

TETO_DE_ORFAOS = 134
"""Quantos nomes exportados por `ui/` ainda não têm chamador em `src/` **nem resposta escrita**.

**Catraca, e ela só desce.** Medido em 2026-09-01, depois das Fases 73 a 77: **136** nomes sem
chamador em 34 módulos, dos quais **2** estão em `SEM_CHAMADOR` -- então **134** ainda são
pergunta. `ui/desenho_do_tabuleiro.py` contribui com um, e ele é um dos dois declarados. Antes das
fases eram **153**, e aquele módulo sozinho respondia por **18**.

O número aqui é o dos **abertos**, e não o total: ver a regra logo abaixo.

> **Este número é maior que o do roadmap, e a diferença é o instrumento.** O `ROADMAP_ESTUDO_QT`
> e a `SPEC_ESTUDO_QT` citam **125**, medidos por busca de texto sobre `src/` -- e ali um nome
> citado num docstring conta como uso. Neste projeto os módulos se descrevem uns aos outros em
> prosa o tempo todo, então a busca de texto **subestima**: pela varredura de identificador, que é
> a que esta guarda usa, eram **153**. `margem_de_coordenada` é o exemplo: ela aparecia num
> docstring de `ui/tokens.py`, e a busca de texto a contava como chamada. Os dois números medem
> coisas diferentes e os dois estão certos; o que vale para a catraca é o estrito.

Cada um é uma pergunta em aberto -- *dar chamador, apagar, tirar do `__all__`, ou isentar com
motivo?* --, e nenhuma delas é respondida por esta guarda. O que ela impede é o número **subir**:
exportar um nome novo que ninguém chama passa a falhar, nomeando o módulo e o nome.
"""


def _identificadores(arvore: ast.AST) -> set[str]:
    """Todo nome que aquele módulo **usa** -- variável, atributo, importado ou apelidado.

    Atributo entra pelo `attr` (`desenho.LARGURA_DA_SETA` conta como uso de `LARGURA_DA_SETA`) e
    o importado pelo `name`, porque `from x import Y` é a forma mais comum de uso neste pacote.
    """
    usados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Name):
            usados.add(no.id)
        elif isinstance(no, ast.Attribute):
            usados.add(no.attr)
        elif isinstance(no, ast.alias):
            usados.add(no.name.split(".")[-1])
            if no.asname:
                usados.add(no.asname)
    return usados


def _exportados(arvore: ast.AST) -> list[str]:
    """O `__all__` daquele módulo, ou vazio. Só literal: um `__all__` montado não é declaração."""
    for no in getattr(arvore, "body", []):
        alvos = getattr(no, "targets", [])
        if isinstance(no, ast.Assign) and any(
            isinstance(alvo, ast.Name) and alvo.id == "__all__" for alvo in alvos
        ):
            if isinstance(no.value, (ast.List, ast.Tuple)):
                return [item.value for item in no.value.elts if isinstance(item, ast.Constant)]
    return []


def orfaos() -> dict[str, list[str]]:
    """`modulo.py -> nomes exportados que nenhum outro módulo de `src/` usa`."""
    arvores = {
        caminho: ast.parse(caminho.read_text(encoding="utf-8")) for caminho in RAIZ.rglob("*.py")
    }
    usos = {caminho: _identificadores(arvore) for caminho, arvore in arvores.items()}

    achados: dict[str, list[str]] = {}
    for modulo in sorted(UI.glob("*.py")):
        if modulo.name == "__init__.py":
            continue
        for nome in _exportados(arvores[modulo]):
            if not any(outro != modulo and nome in nomes for outro, nomes in usos.items()):
                achados.setdefault(modulo.name, []).append(nome)
    return achados


def _rotulos(achados: dict[str, list[str]]) -> set[str]:
    return {f"{modulo.removesuffix('.py')}.{nome}" for modulo, nomes in achados.items() for nome in nomes}


class DecisaoOrfaTests(unittest.TestCase):
    """A pergunta que nada fazia, feita."""

    def setUp(self) -> None:
        self.achados = orfaos()
        self.rotulos = _rotulos(self.achados)

    def test_a_varredura_nao_e_vacua(self) -> None:
        """Sem isto, um leitor que deixasse de achar `__all__` faria os outros passarem sobre nada.

        É a lição da S-506: ~20 varreduras ficaram verdes no corte **por passarem sobre lista
        vazia**, e nenhuma delas falhou para dizer isso.
        """
        arvores = [ast.parse(c.read_text(encoding="utf-8")) for c in sorted(UI.glob("*.py"))]
        exportados = sum(len(_exportados(a)) for a in arvores)
        self.assertGreater(exportados, 300, "o leitor de `__all__` deixou de achar os nomes")
        self.assertGreater(len(self.rotulos), 0, "a varredura não achou nenhum órfão -- suspeito")

    def test_o_modulo_do_desenho_nao_tem_decisao_orfa(self) -> None:
        """O módulo que a Fase 73 triou. **Zero**, salvo o que estiver declarado com motivo.

        Ele tinha 18 em 2026-09-01: os doze apelidos de cor (apagados), `COORD_FONT`,
        `COORD_OFFSET_PX`, `margem_de_coordenada`, `LARGURA_DA_SETA` e `PAPEL_DE_SETA` (que
        ganharam chamador nas S-508 e S-510), mais `HEATMAP_LOW`/`HEATMAP_HIGH`, que saíram do
        `__all__` por não serem API -- `heatmap_color` é quem as usa, e ela é a decisão.
        """
        sobraram = sorted(
            rotulo
            for rotulo in _rotulos({"desenho_do_tabuleiro.py": self.achados.get("desenho_do_tabuleiro.py", [])})
            if rotulo not in SEM_CHAMADOR
        )
        self.assertEqual([], sobraram, "decisão pura do desenho sem quem a chame")

    def test_a_excecao_declarada_ainda_e_orfa(self) -> None:
        """O outro lado do mapa: quem ganhou chamador **sai** da lista.

        Sem isto, `SEM_CHAMADOR` viraria o lugar onde a pergunta deixa de ser feita -- e a lista
        cresceria a cada item, que é o oposto do que ela existe para fazer.
        """
        problemas = [
            f"{rotulo} está em SEM_CHAMADOR e já tem chamador"
            for rotulo in SEM_CHAMADOR
            if rotulo not in self.rotulos
        ]
        problemas += [f"{rotulo} está isento sem motivo escrito" for rotulo, m in SEM_CHAMADOR.items() if not m.strip()]
        self.assertEqual([], problemas)

    def test_a_catraca_nao_sobe(self) -> None:
        """O número não pode crescer. Quando alguém tria um, o número desce e a catraca acompanha.

        **Conta o que ainda é pergunta**, e não todo órfão: quem está em `SEM_CHAMADOR` já foi
        olhado e respondido. Ver o docstring de `TETO_DE_ORFAOS`.
        """
        abertos = sorted(self.rotulos - set(SEM_CHAMADOR))
        self.assertLessEqual(
            len(abertos),
            TETO_DE_ORFAOS,
            f"{len(abertos)} nomes exportados sem chamador nem motivo escrito, contra a catraca "
            f"de {TETO_DE_ORFAOS}. Um nome novo em `__all__` precisa de quem o chame -- ou de uma "
            "linha em SEM_CHAMADOR com o motivo.\nOs de agora:\n  " + "\n  ".join(abertos),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
