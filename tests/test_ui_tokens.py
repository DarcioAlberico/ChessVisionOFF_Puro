"""A paleta num lugar só, e cada par de cores com a razão medida (S-145, S-146).

**Por que os dois itens dividem um arquivo.** A S-145 declara os pares; a S-146 mede se eles
passam. Um par que reprova é defeito da paleta e não do painel que a usou — separar os testes
faria a medição olhar para um lugar e a correção acontecer em outro.

Nada aqui abre janela: `ui/tokens.py` não importa `tkinter` de propósito, e é o que permite
afirmar a paleta inteira em milissegundos.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from chess_diagram_ocr.ui import tokens
from chess_diagram_ocr.ui.tokens import (
    AA_GRAFICO,
    AA_TEXTO,
    PAPEIS,
    RESERVA,
    cor,
    paleta,
    razao_de_contraste,
    sobre_superficie,
)

RAIZ = Path(__file__).resolve().parents[1]
HEX = re.compile(r'"#[0-9a-fA-F]{6}"')

PARES_DE_TEXTO = (
    (tokens.TEXTO_SECUNDARIO, tokens.SUPERFICIE_PADRAO),
    (tokens.PRONTO_TEXTO, tokens.SUPERFICIE_PADRAO),
    (tokens.PROBLEMA_TEXTO, tokens.SUPERFICIE_PADRAO),
    (tokens.ATENCAO, tokens.SUPERFICIE_PADRAO),
    (tokens.DIVERGENTE_TEXTO, tokens.SUPERFICIE_PADRAO),
    (tokens.VIZINHA_TEXTO, tokens.SUPERFICIE_PADRAO),
    (tokens.TEXTO_PADRAO, tokens.SUPERFICIE_PADRAO),
)
"""Todo par (texto, fundo) que a janela de fato desenha. Piso AA de 4,5:1.

**Dois deles trocaram de papel na S-224**: `PROBLEMA` e `DIVERGENTE` viraram `PROBLEMA_TEXTO` e
`DIVERGENTE_TEXTO`. Os dois primeiros são contorno de casa no tabuleiro, e estavam aqui fazendo
dois trabalhos com um nome -- o que passou despercebido enquanto o mesmo valor servia aos dois.

**A lista encolheu na S-147, e por honestidade.** Metade dela media texto contra
`SUPERFICIE_TABULEIRO`, e a janela nunca escreveu uma letra ali: os rótulos de material, de
legalidade e de procedência moram em `ttk.Frame`, não no canvas do tabuleiro. O único texto
sobre a esteira são as coordenadas, e elas não têm cor fixa a medir — `sobre_superficie` as
resolve contra o fundo real, que é o teste logo abaixo.

Manter os pares falsos custava mais do que não medir nada: com a esteira escura da S-147 eles
reprovariam, e a correção seria clarear a esteira por causa de um texto que não existe."""

PARES_DE_MARCACAO = (
    (tokens.PRONTO, tokens.SUPERFICIE_PAGINA),
    (tokens.A_FAZER, tokens.SUPERFICIE_PAGINA),
    (tokens.LIDO, tokens.SUPERFICIE_PAGINA),
    (tokens.DISPENSADO, tokens.SUPERFICIE_PAGINA),
    (tokens.TRACEJADO, tokens.SUPERFICIE_PAGINA),
)
"""Borda de retângulo sobre a página. Piso de elemento gráfico, 3:1 -- não é texto."""


class ContrasteTests(unittest.TestCase):
    """A razão WCAG 2.1, e os pares que ela reprovava (S-146)."""

    def test_as_ancoras_conhecidas(self) -> None:
        """Sem elas, um erro na fórmula passaria despercebido e reprovaria a paleta inteira."""
        self.assertAlmostEqual(razao_de_contraste("#000000", "#ffffff"), 21.0, places=2)
        self.assertAlmostEqual(razao_de_contraste("#777777", "#ffffff"), 4.48, places=2)
        self.assertAlmostEqual(razao_de_contraste("#ffffff", "#ffffff"), 1.0, places=6)

    def test_a_razao_e_simetrica(self) -> None:
        self.assertAlmostEqual(
            razao_de_contraste("#146c43", "#f2f2f2"), razao_de_contraste("#f2f2f2", "#146c43"), places=9
        )

    def test_todo_par_de_texto_passa_o_piso_aa(self) -> None:
        reprovados = [
            f"{texto} sobre {fundo}: {razao_de_contraste(RESERVA[texto], RESERVA[fundo]):.2f}:1"
            for texto, fundo in PARES_DE_TEXTO
            if razao_de_contraste(RESERVA[texto], RESERVA[fundo]) < AA_TEXTO
        ]
        self.assertEqual([], reprovados, f"pares abaixo de {AA_TEXTO}:1")

    def test_toda_marcacao_passa_o_piso_grafico(self) -> None:
        reprovados = [
            f"{marca} sobre {fundo}: {razao_de_contraste(RESERVA[marca], RESERVA[fundo]):.2f}:1"
            for marca, fundo in PARES_DE_MARCACAO
            if razao_de_contraste(RESERVA[marca], RESERVA[fundo]) < AA_GRAFICO
        ]
        self.assertEqual([], reprovados, f"marcações abaixo de {AA_GRAFICO}:1")

    def test_o_verde_de_marcacao_reprovaria_como_texto(self) -> None:
        """A razão de `PRONTO` e `PRONTO_TEXTO` serem dois papéis, dita com número.

        `#00c07a` sobre branco dá **2,38:1**: serve de borda sobre a página escura (7,16:1) e
        não serve de texto. Juntá-los de volta num papel só reintroduz o defeito da S-146.
        """
        self.assertLess(razao_de_contraste(RESERVA[tokens.PRONTO], "#ffffff"), AA_TEXTO)
        self.assertGreaterEqual(razao_de_contraste(RESERVA[tokens.PRONTO_TEXTO], "#ffffff"), AA_TEXTO)

    def test_a_coordenada_e_legivel_em_toda_superficie_de_canvas(self) -> None:
        """O defeito que a S-146 chama de o pior dos dois: as letras a–h desenhadas e invisíveis.

        A constante era `#d8d8d8`, escolhida para o tabuleiro escuro da Análise. Sobre o
        `#f2f2f2` que o Resultado usava então, **1,27:1**.

        A varredura passou a ser sobre `SUPERFICIES` inteira, nos **dois** temas: depois da
        S-147 cada fundo de canvas tem dois valores, e um deles legível não diz nada sobre o
        outro.
        """
        antiga, antigo_fundo = "#d8d8d8", "#f2f2f2"
        self.assertLess(razao_de_contraste(antiga, antigo_fundo), 1.5)

        for papel in tokens.SUPERFICIES:
            for tema, fundo in (("claro", RESERVA[papel]), ("escuro", tokens._NO_ESCURO[papel])):
                with self.subTest(superficie=papel, tema=tema):
                    escolhida = sobre_superficie(fundo)
                    razao = razao_de_contraste(escolhida, fundo)
                    self.assertGreaterEqual(razao, AA_TEXTO, f"{escolhida} sobre {papel}/{tema}: {razao:.2f}:1")

    def test_a_coordenada_escolhe_lados_opostos_para_fundos_opostos(self) -> None:
        """Se a função devolvesse a mesma cor nos dois, ela não estaria resolvendo nada."""
        clara = sobre_superficie(RESERVA[tokens.SUPERFICIE_TABULEIRO])
        escura = sobre_superficie(RESERVA[tokens.SUPERFICIE_DICA])
        self.assertNotEqual(clara, escura)


class PaletaTests(unittest.TestCase):
    """Um papel, um hex; e a resolução é total (S-145)."""

    def test_todo_papel_tem_reserva(self) -> None:
        self.assertEqual(set(PAPEIS), set(RESERVA), "PAPEIS e RESERVA divergiram")

    def test_a_paleta_resolve_sem_tema(self) -> None:
        resolvida = paleta(None)
        self.assertEqual(set(resolvida), set(PAPEIS))
        self.assertTrue(all(valor.startswith("#") and len(valor) == 7 for valor in resolvida.values()))

    def test_papel_desconhecido_levanta_em_vez_de_devolver_cinza(self) -> None:
        """Um papel escrito errado que resolvesse para *alguma* cor viraria um widget de cor
        plausível e sem significado -- que é o estado de que a S-145 veio tirar o projeto."""
        with self.assertRaises(KeyError):
            cor("VERDE_BONITO")

    COINCIDEM_DE_PROPOSITO: tuple[frozenset[str], ...] = ()
    """Os pares que **devem** ter a mesma cor na paleta clara. **Vazio desde a S-295.**

    Ele existia com dois pares -- `PROBLEMA`/`PROBLEMA_TEXTO` e `DIVERGENTE`/`DIVERGENTE_TEXTO` --,
    separados na S-224 quando o cromo escuro pediu valores opostos: a letra precisa clarear para
    ser lida e o contorno precisa **não** clarear, porque ele é medido contra as casas, que não
    seguem pele nenhuma. Na paleta clara os dois coincidiam porque **um valor servia aos dois**, e
    inventar uma diferença só para separar os nomes teria mudado pixel de hoje sem medida pedindo.

    **A medida chegou** (S-295): o contorno dava 1,73:1 e 1,86:1 sobre a casa escura -- borda
    desenhada e invisível em metade do tabuleiro. Escurecê-lo afastou os pares na paleta clara
    também, e a exceção deixou de ser necessária. A separação da S-224 estava certa e agora é real
    em toda pele.

    A tupla fica, vazia, porque o dia em que dois papéis precisarem mesmo da mesma cor é aqui que
    o motivo se escreve."""

    def test_dois_papeis_de_significado_diferente_nao_compartilham_hex(self) -> None:
        """"Três verdes com três significados de bom" era o achado; o inverso também é defeito.

        As exceções declaradas são as que **devem** coincidir. Se um dia duas entradas
        precisarem da mesma cor, o par entra em `COINCIDEM_DE_PROPOSITO` com o motivo.
        """
        por_cor: dict[str, list[str]] = {}
        for papel, valor in RESERVA.items():
            por_cor.setdefault(valor, []).append(papel)
        repetidas = {
            valor: papeis
            for valor, papeis in por_cor.items()
            if len(papeis) > 1 and frozenset(papeis) not in self.COINCIDEM_DE_PROPOSITO
        }
        self.assertEqual({}, repetidas, "dois papéis resolvendo para a mesma cor")

    def test_o_par_declarado_deixa_de_coincidir_no_cromo_escuro(self) -> None:
        """A exceção acima só valeria na paleta clara. Com ela vazia, o laço não roda -- e o que
        garante a separação passou a ser o teste abaixo, que vale nas duas paletas."""
        for par in self.COINCIDEM_DE_PROPOSITO:
            marcacao, letra = sorted(par, key=len)
            with self.subTest(par=sorted(par)):
                self.assertEqual(RESERVA[marcacao], RESERVA[letra])
                self.assertNotEqual(
                    cor(marcacao, cromo_escuro=True),
                    cor(letra, cromo_escuro=True),
                )

    def test_o_contorno_e_a_letra_do_mesmo_significado_nao_compartilham_valor(self) -> None:
        """A separação da S-224, agora real em **toda** paleta (S-295).

        Contorno de casa e letra são medidos contra fundos diferentes -- as casas, que não seguem
        pele, e o cromo, que segue. Enquanto um valor servia aos dois a diferença era só de nome;
        desde que o contorno escureceu para ser visível na casa escura, ela é de tinta.
        """
        for marcacao, letra in (
            (tokens.PROBLEMA, tokens.PROBLEMA_TEXTO),
            (tokens.DIVERGENTE, tokens.DIVERGENTE_TEXTO),
        ):
            with self.subTest(par=(marcacao, letra)):
                self.assertNotEqual(RESERVA[marcacao], RESERVA[letra])
                self.assertNotEqual(
                    cor(marcacao, cromo_escuro=True), cor(letra, cromo_escuro=True)
                )

    def test_o_tema_vence_a_reserva_quando_responde(self) -> None:
        class EstiloFalso:
            def lookup(self, layout: str, option: str) -> str:
                return "#0b5ed7" if layout == "success.TLabel" else ""

        self.assertEqual(cor(tokens.PRONTO_TEXTO, EstiloFalso()), "#0b5ed7")
        self.assertEqual(cor(tokens.PROBLEMA, EstiloFalso()), RESERVA[tokens.PROBLEMA])

    def test_o_tema_que_so_herda_a_cor_do_estilo_base_nao_esta_respondendo(self) -> None:
        """O defeito que o rodapé da S-163 expôs, e ele valia para os três papéis de texto.

        `style.lookup` sobe a cadeia de herança do Tk: um `danger.TLabel` que não declara
        `foreground` devolve o do `TLabel` sem dizer que não tinha o seu. Sob `bootstrap-light` os
        três papéis de `_DO_TEMA` resolviam para o **mesmo** `#212529` -- "já salvo", "posição
        ilegal" e contagem de apoio na mesma cor, e as três medidas da S-146 sem chegar à tela.
        """

        class EstiloQueSoHerda:
            def lookup(self, layout: str, option: str) -> str:
                return "#212529"

        for papel in tokens._DO_TEMA:
            with self.subTest(papel=papel):
                self.assertEqual(cor(papel, EstiloQueSoHerda()), RESERVA[papel])

    def test_os_tres_papeis_de_texto_do_tema_sao_distintos_entre_si(self) -> None:
        """A propriedade que o usuário vê, e a que estava falsa: três significados, três cores."""

        class EstiloQueSoHerda:
            def lookup(self, layout: str, option: str) -> str:
                return "#212529"

        resolvidas = {cor(papel, EstiloQueSoHerda()) for papel in tokens._DO_TEMA}
        self.assertEqual(len(resolvidas), len(tokens._DO_TEMA))

    def test_o_tema_que_levanta_nao_derruba_a_janela(self) -> None:
        """Aparência não pode derrubar ferramenta -- é o contrato do `ui/theme.py` desde a S-53."""

        class EstiloQuebrado:
            def lookup(self, layout: str, option: str) -> str:
                raise RuntimeError("tema exótico")

        self.assertEqual(cor(tokens.PRONTO_TEXTO, EstiloQuebrado()), RESERVA[tokens.PRONTO_TEXTO])

    def test_o_tema_que_responde_lixo_cai_na_reserva(self) -> None:
        class EstiloVago:
            def lookup(self, layout: str, option: str) -> str:
                return "SystemButtonFace"

        self.assertEqual(cor(tokens.TEXTO_SECUNDARIO, EstiloVago()), RESERVA[tokens.TEXTO_SECUNDARIO])


class SemHexCravadoTests(unittest.TestCase):
    """A varredura que impede a regressão: 25 cores em 8 arquivos não podem voltar.

    É o critério de aceite da S-145 escrito como teste. Sem ele, a próxima cor entra cravada
    exatamente como as 25 entraram -- uma de cada vez, cada uma justificável sozinha.
    """

    def _arquivos(self) -> list[Path]:
        return [
            *sorted((RAIZ / "src" / "chess_diagram_ocr" / "ui").glob("*.py")),
            *sorted((RAIZ / "src" / "chess_diagram_ocr" / "qt").glob("*.py")),
        ]

    def test_so_o_modulo_de_tokens_escreve_hexadecimal(self) -> None:
        infratores = []
        for arquivo in self._arquivos():
            if arquivo.name == "tokens.py":
                continue
            for numero, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
                if HEX.search(linha):
                    infratores.append(f"{arquivo.name}:{numero}: {linha.strip()[:70]}")
        self.assertEqual(
            [],
            infratores,
            "cor cravada fora de ui/tokens.py. Declare um papel lá e peça o papel aqui.",
        )

    def test_a_varredura_enxerga_o_que_deveria(self) -> None:
        """O controle: se o `tokens.py` deixasse de casar, o teste acima passaria vazio."""
        texto = (RAIZ / "src" / "chess_diagram_ocr" / "ui" / "tokens.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(len(HEX.findall(texto)), len(PAPEIS))


if __name__ == "__main__":
    unittest.main()
