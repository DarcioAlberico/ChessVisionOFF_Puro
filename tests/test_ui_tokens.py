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
    (tokens.TEXTO_SECUNDARIO, tokens.SUPERFICIE_TABULEIRO),
    (tokens.TEXTO_SECUNDARIO, tokens.SUPERFICIE_PADRAO),
    (tokens.PRONTO_TEXTO, tokens.SUPERFICIE_TABULEIRO),
    (tokens.PRONTO_TEXTO, tokens.SUPERFICIE_PADRAO),
    (tokens.PROBLEMA, tokens.SUPERFICIE_TABULEIRO),
    (tokens.ATENCAO, tokens.SUPERFICIE_TABULEIRO),
    (tokens.DIVERGENTE, tokens.SUPERFICIE_PADRAO),
    (tokens.CORRIGIDO_TEXTO, tokens.SUPERFICIE_PADRAO),
    (tokens.TEXTO_PADRAO, tokens.SUPERFICIE_PADRAO),
)
"""Todo par (texto, fundo) que a janela de fato desenha. Piso AA de 4,5:1."""

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

    def test_a_coordenada_e_legivel_nas_duas_superficies_de_tabuleiro(self) -> None:
        """O defeito que a S-146 chama de o pior dos dois: as letras a–h desenhadas e invisíveis.

        A constante era `#d8d8d8`, escolhida para o tabuleiro escuro da Análise. Sobre o
        `#f2f2f2` do Resultado dá **1,27:1**.
        """
        antiga = "#d8d8d8"
        self.assertLess(razao_de_contraste(antiga, RESERVA[tokens.SUPERFICIE_TABULEIRO]), 1.5)

        for superficie in (tokens.SUPERFICIE_TABULEIRO, tokens.SUPERFICIE_ESTUDO):
            with self.subTest(superficie=superficie):
                escolhida = sobre_superficie(RESERVA[superficie])
                razao = razao_de_contraste(escolhida, RESERVA[superficie])
                self.assertGreaterEqual(razao, AA_TEXTO, f"{escolhida} sobre {superficie}: {razao:.2f}:1")

    def test_a_coordenada_escolhe_lados_opostos_para_fundos_opostos(self) -> None:
        """Se a função devolvesse a mesma cor nos dois, ela não estaria resolvendo nada."""
        clara = sobre_superficie(RESERVA[tokens.SUPERFICIE_ESTUDO])
        escura = sobre_superficie(RESERVA[tokens.SUPERFICIE_TABULEIRO])
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

    def test_dois_papeis_de_significado_diferente_nao_compartilham_hex(self) -> None:
        """"Três verdes com três significados de bom" era o achado; o inverso também é defeito.

        As exceções declaradas são as que **devem** coincidir: nada, hoje. Se um dia duas
        entradas precisarem da mesma cor, o par entra aqui com o motivo.
        """
        por_cor: dict[str, list[str]] = {}
        for papel, valor in RESERVA.items():
            por_cor.setdefault(valor, []).append(papel)
        repetidas = {valor: papeis for valor, papeis in por_cor.items() if len(papeis) > 1}
        self.assertEqual({}, repetidas, "dois papéis resolvendo para a mesma cor")

    def test_o_tema_vence_a_reserva_quando_responde(self) -> None:
        class EstiloFalso:
            def lookup(self, layout: str, option: str) -> str:
                return "#0b5ed7" if layout == "success.TLabel" else ""

        self.assertEqual(cor(tokens.PRONTO_TEXTO, EstiloFalso()), "#0b5ed7")
        self.assertEqual(cor(tokens.PROBLEMA, EstiloFalso()), RESERVA[tokens.PROBLEMA])

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
        return [*sorted((RAIZ / "src" / "chess_diagram_ocr" / "ui").glob("*.py")), RAIZ / "app_tkinter.py"]

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


class CoordenadaNoCanvasTests(unittest.TestCase):
    """A coordenada resolvida contra o canvas de verdade, com Tk (S-146).

    O teste puro acima prova a função; este prova a **ligação** -- que o desenho pergunta ao
    canvas em que está, em vez de usar a constante. Sem ele, `_cor_de_coordenada` podia existir
    e não ser chamada, que é como a constante sobreviveu até aqui.
    """

    @classmethod
    def setUpClass(cls) -> None:
        import tkinter as tk

        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:  # pragma: no cover - maquina sem display
            raise unittest.SkipTest(f"sem Tk disponível: {exc}") from exc
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.root.destroy()

    def _cor_no_fundo(self, fundo: str) -> str:
        import tkinter as tk

        from chess_diagram_ocr.ui.board_render import BoardRenderer

        canvas = tk.Canvas(self.root, background=fundo)
        try:
            return BoardRenderer._cor_de_coordenada(canvas)
        finally:
            canvas.destroy()

    def test_o_tabuleiro_claro_recebe_coordenada_escura(self) -> None:
        clara = RESERVA[tokens.SUPERFICIE_TABULEIRO]
        escolhida = self._cor_no_fundo(clara)
        self.assertGreaterEqual(razao_de_contraste(escolhida, clara), AA_TEXTO)

    def test_o_tabuleiro_escuro_recebe_coordenada_clara(self) -> None:
        escuro = RESERVA[tokens.SUPERFICIE_ESTUDO]
        escolhida = self._cor_no_fundo(escuro)
        self.assertGreaterEqual(razao_de_contraste(escolhida, escuro), AA_TEXTO)

    def test_um_fundo_nomeado_pelo_sistema_tambem_resolve(self) -> None:
        """`SystemButtonFace` não é hexadecimal: sem a conversão, a função levantaria."""
        escolhida = self._cor_no_fundo("white")
        self.assertGreaterEqual(razao_de_contraste(escolhida, "#ffffff"), AA_TEXTO)
