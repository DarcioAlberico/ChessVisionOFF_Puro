"""O espaço do interior dos painéis como dado, e não como pixel cravado (S-447).

**O que estes testes travam.**

- os quatro papéis resolvem contra a fonte **e** a densidade em vigor, e quem as fixa é uma
  função só -- `theme.registrar_estilos`, no mesmo ponto em que aplica a folha da S-441;
- o interior dos painéis **não tem mais literal de espaço**, salvo três sítios registrados aqui
  com o motivo -- e é a lista de exceções que impede a varredura de virar decoração;
- e o alcance real da densidade fica dito, em vez de prometido: ela chega ao interior na
  **abertura seguinte**, porque `pack` não reaplica opção e os painéis não são remontados.
"""

from __future__ import annotations

import collections
import io
import pathlib
import re
import tokenize
import unittest

from chess_diagram_ocr.ui import espaco, pele, tipografia

RAIZ = pathlib.Path(__file__).resolve().parents[1]
ALVOS = [*sorted((RAIZ / "src" / "chess_diagram_ocr" / "ui").glob("*.py")), RAIZ / "app_tkinter.py"]

PADROES = (
    re.compile(r"\bpad([xy])=\((\d+),\s*(\d+)\)"),
    re.compile(r"\bpad([xy])=(\d+)\b"),
    re.compile(r"\bpadding=\((\d+),\s*(\d+)\)"),
    re.compile(r"\bpadding=(\d+)\b"),
)


def _protegido(src: str) -> dict[int, list[tuple[int, int]]]:
    """`linha -> faixas de coluna` de STRING e COMMENT.

    **Sem isto a varredura acusa prosa.** `ui/folha.py` e `ui/tipografia.py` *documentam*
    `padx=10` e `padding=(6, 2)` em docstring, e uma regex por linha não sabe a diferença entre
    documentar um número e cravá-lo.
    """
    faixas: dict[int, list[tuple[int, int]]] = collections.defaultdict(list)
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type not in (tokenize.STRING, tokenize.COMMENT):
            continue
        (l0, c0), (l1, c1) = tok.start, tok.end
        for linha in range(l0, l1 + 1):
            faixas[linha].append((c0 if linha == l0 else 0, c1 if linha == l1 else 10**6))
    return faixas


class EscalaTests(unittest.TestCase):
    """A parte pura. Nenhum destes precisa de janela."""

    def setUp(self) -> None:
        base, densidade = espaco.vigente()
        self.addCleanup(espaco.ajustar, base=base, densidade=densidade)

    def test_os_quatro_papeis_sao_a_janela_de_hoje_na_base_de_referencia(self) -> None:
        """**A confortável não *parece* a janela de hoje: ela é.** Os quatro números são os que já
        estavam cravados nos `pack`, e é o que faz esta conversão não mudar um pixel."""
        espaco.ajustar(base=tipografia.BASE_DE_REFERENCIA, densidade=pele.CONFORTAVEL)
        self.assertEqual((14, 10, 6, 2), (espaco.moldura(), espaco.folga(), espaco.linha(), espaco.minima()))

    def test_o_espaco_acompanha_a_fonte_do_sistema(self) -> None:
        """Quem aumenta a fonte do Windows quer o programa maior, e não mais apertado (S-149)."""
        espaco.ajustar(base=9, densidade=pele.CONFORTAVEL)
        pequeno = (espaco.moldura(), espaco.folga(), espaco.linha(), espaco.minima())
        espaco.ajustar(base=12, densidade=pele.CONFORTAVEL)
        grande = (espaco.moldura(), espaco.folga(), espaco.linha(), espaco.minima())
        for antes, depois in zip(pequeno, grande, strict=True):
            self.assertGreater(depois, antes)

    def test_a_compacta_encolhe_e_nunca_chega_a_zero(self) -> None:
        espaco.ajustar(base=9, densidade=pele.CONFORTAVEL)
        confortavel = (espaco.moldura(), espaco.folga(), espaco.linha(), espaco.minima())
        espaco.ajustar(base=9, densidade=pele.COMPACTA)
        compacta = (espaco.moldura(), espaco.folga(), espaco.linha(), espaco.minima())
        for menor, maior in zip(compacta, confortavel, strict=True):
            self.assertLess(menor, maior)
            self.assertGreaterEqual(menor, 1)

    def test_densidade_desconhecida_levanta_sem_deixar_o_modulo_pela_metade(self) -> None:
        """Levanta **antes** de guardar: uma chamada errada não pode deixar a base trocada e a
        densidade não, que é um estado que nenhum teste seguinte explicaria."""
        espaco.ajustar(base=9, densidade=pele.CONFORTAVEL)
        with self.assertRaises(KeyError):
            espaco.ajustar(base=11, densidade="folgada")
        self.assertEqual((9, pele.CONFORTAVEL), espaco.vigente())


class SemLiteralTests(unittest.TestCase):
    """O critério de aceite da S-447, e a lista que o mantém honesto."""

    EXCECOES = {
        ("legenda.py", "padx=(0, 18)"): "a calha entre a tecla e a descrição na grade da legenda: "
        "é separação de coluna de tabela, e não vão entre vizinhos",
        ("rodape.py", "padding=(8, 3)"): "o rodapé é deliberadamente fino, e 3 fica entre "
        "FOLGA_MINIMA (2) e FOLGA_DE_LINHA (6) -- nenhum dos dois é o que ele quer",
        ("scan_scope.py", "padx=(22, 0)"): "recuo que alinha o rótulo sob o texto de um "
        "`Checkbutton`, e não vão: ele depende da largura do indicador, não da escala",
    }
    """Os três literais que **não** couberam em papel nenhum, e por quê.

    A spec da S-447 previu o caso e proibiu a saída fácil: *"onde um literal não couber em nenhum
    papel, o item não inventa papel"*. Inventar um quinto papel para servir a três sítios seria
    trocar três números soltos por uma escala que não descreve mais a janela.
    """

    def test_nenhum_literal_de_espaco_fora_das_excecoes(self) -> None:
        sobraram = []
        for arquivo in ALVOS:
            src = arquivo.read_text(encoding="utf-8")
            vetadas = _protegido(src)
            for numero, linha in enumerate(src.splitlines(), 1):
                for padrao in PADROES:
                    for achado in padrao.finditer(linha):
                        if any(a <= achado.start() < b for a, b in vetadas.get(numero, [])):
                            continue
                        if (arquivo.name, achado.group(0)) in self.EXCECOES:
                            continue
                        sobraram.append(f"{arquivo.name}:{numero}  {achado.group(0)}")
        self.assertEqual([], sobraram, "literal de espaço fora da escala: use `ui/espaco.py`")

    def test_toda_excecao_declarada_ainda_existe(self) -> None:
        """Exceção que sobra é exceção que esconde: se o sítio sumiu, a entrada sai junto."""
        vivos = set()
        for arquivo in ALVOS:
            src = arquivo.read_text(encoding="utf-8")
            for (nome, trecho) in self.EXCECOES:
                if arquivo.name == nome and trecho in src:
                    vivos.add((nome, trecho))
        self.assertEqual(set(self.EXCECOES), vivos)

    def test_a_varredura_enxerga_um_literal_plantado(self) -> None:
        """Uma varredura que não achasse nada passaria em verde para sempre."""
        achou = any(padrao.search("linha.pack(padx=6, pady=(4, 0))") for padrao in PADROES)
        self.assertTrue(achou)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
