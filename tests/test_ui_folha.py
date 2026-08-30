"""A folha de base do `ttk` (S-441) e o vão do indicador (S-442).

**O que estes testes travam.**

- a folha é **derivada da escala de folga**, e não uma segunda tabela de pixels -- é a mesma trava
  que a S-232 pôs na densidade e a S-149 no tamanho de fonte;
- ela alcança **quem o tema deixou vazio**, e a fronteira é afirmável: um dia em que o
  `ttkbootstrap` passe a tematizar a faixa de abas, é aqui que isso aparece;
- ela chega **igual às três peles**, que é a regra 1 da `SPEC_ACABAMENTO.md` e o defeito que a
  S-441 veio corrigir -- o `padding=(14, 6)` da aba existia desde a S-226 e era entregue a uma
  pele só;
- e ela **não derruba a janela** quando o tema recusa uma opção, que é o contrato de `ui/theme.py`
  com um dono a mais.

A assertiva de densidade e a de troca de pele moram aqui, e não em `test_ui_densidade.py` e
`test_ui_troca_de_pele.py` como a spec sugeria: as duas afirmam coisas sobre a *folha*, e a folha
tem arquivo. Os dois vizinhos continuam donos do que era deles.
"""

from __future__ import annotations

import tkinter as tk
import unittest
from tkinter import ttk
from unittest.mock import patch

from tk_root import raiz

from chess_diagram_ocr.ui import folha, pele, theme, tipografia


def _par(bruto: object) -> tuple[int, ...]:
    """O `padding` que o Tk devolve, como par de inteiros.

    O `lookup` devolve `'14 6'`, `('14', '6')` ou `14` conforme a opção e o tema, e comparar
    contra `str` faria o teste passar por acidente na primeira e falhar na segunda.
    """
    if isinstance(bruto, str):
        return tuple(int(pedaco) for pedaco in bruto.split())
    if isinstance(bruto, (list, tuple)):
        return tuple(int(str(pedaco)) for pedaco in bruto)
    return (int(str(bruto)),)


class EscalaTests(unittest.TestCase):
    """A parte pura. Afirmável em 7, 9 e 12 sem abrir janela, como `tipografia.folga`."""

    def test_todo_numero_da_folha_sai_da_escala_de_folga(self) -> None:
        """**É o item.** Uma folha com pixel cravado seria uma segunda tabela a manter, e a
        primeira fonte de sistema diferente a deixaria mentindo -- que é o argumento com que a
        S-149 derivou o tamanho da fonte e a S-232 o espaço do cromo."""
        for base in (7, 9, 12):
            for densidade in pele.DENSIDADES:
                escala = tipografia.folgas(base=base, densidade=densidade)
                for classe, (horizontal, vertical) in folha.RECHEIO.items():
                    with self.subTest(classe=classe, base=base, densidade=densidade):
                        self.assertEqual(
                            (escala[horizontal], escala[vertical]),
                            folha.recheio(classe, base=base, densidade=densidade),
                        )

    def test_a_folga_da_aba_e_a_que_a_S226_mediu(self) -> None:
        """**A folha não inventa a folga da aba: ela generaliza a que já passou por revisão.**

        `(14, 6)` é o valor que a S-226 mediu para a faixa da pele "Foco" e que ficou um ano
        entregue a uma pele só. Se este número mudar, mudou por decisão de alguém -- e não porque
        um papel de folga foi trocado sem que ninguém olhasse a aba.
        """
        self.assertEqual(
            (14, 6),
            folha.recheio("TNotebook.Tab", base=tipografia.BASE_DE_REFERENCIA),
        )

    def test_a_folha_encolhe_na_compacta_e_nunca_chega_a_zero(self) -> None:
        """Dois vizinhos colados viram um controle só para o olho (`tipografia.FOLGA_MINIMA`)."""
        for classe in folha.CLASSES:
            confortavel = folha.recheio(classe, densidade=pele.CONFORTAVEL)
            compacta = folha.recheio(classe, densidade=pele.COMPACTA)
            with self.subTest(classe=classe):
                self.assertLess(compacta, confortavel)
                self.assertTrue(all(valor >= 1 for valor in compacta))
        for base in (1, 4, 7, 9):
            for densidade in pele.DENSIDADES:
                with self.subTest(base=base, densidade=densidade):
                    self.assertGreaterEqual(folha.vao_do_indicador(base=base, densidade=densidade), 1)

    def test_o_vao_do_indicador_acompanha_a_fonte(self) -> None:
        self.assertGreater(folha.vao_do_indicador(base=12), folha.vao_do_indicador(base=9))
        self.assertLess(
            folha.vao_do_indicador(densidade=pele.COMPACTA),
            folha.vao_do_indicador(densidade=pele.CONFORTAVEL),
        )

    def test_classe_fora_da_folha_levanta(self) -> None:
        """A disciplina de `tokens.cor` e de `estilos.estilo_de_botao`: uma classe escrita errada
        que caísse em `(0, 0)` desenharia o widget de fábrica, e ninguém saberia dizer se aquilo
        era a folha ou a ausência dela."""
        with self.assertRaises(KeyError) as erro:
            folha.recheio("TCoisa")
        self.assertIn("CLASSES", str(erro.exception))
        with self.assertRaises(KeyError):
            folha.recheio("TCheckbutton", densidade="folgada")

    def test_a_folha_nao_encosta_em_quem_o_tema_ja_resolve(self) -> None:
        """**A fronteira do módulo, dita como teste.**

        `bootstrap-light` já dá `10 4` ao `TButton`, `5` ao `TEntry` e `10 4 6 4` ao
        `TMenubutton`. Escrever a folha sobre eles foi medido e piora: com `(6, 2)` o botão de
        fita encolhe de 58 para 50 px, porque 6 é menos que os 10 que o tema já dava. Se alguém
        acrescentar um deles aqui, é este teste que pergunta se mediu.
        """
        for classe in ("TButton", "TEntry", "TCombobox", "TMenubutton", "TFrame"):
            with self.subTest(classe=classe):
                self.assertNotIn(classe, folha.CLASSES)


class NoStyleTests(unittest.TestCase):
    """O que só se confere com um `Style` de verdade."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.addCleanup(lambda: theme.apply_theme(self.root, densidade=pele.CONFORTAVEL))

    def test_a_folha_entra_no_style_pelas_duas_peles_de_tema(self) -> None:
        for escuro in (False, True):
            theme.apply_theme(self.root, cromo_escuro=escuro)
            estilo = theme.estilo_atual()
            if estilo is None:  # pragma: no cover - sem ttk não há folha a conferir
                self.skipTest("sem Style disponível")
            for classe in folha.CLASSES:
                with self.subTest(classe=classe, cromo_escuro=escuro):
                    self.assertEqual(
                        folha.recheio(classe, base=theme.fonte_base()[0]),
                        _par(estilo.lookup(classe, "padding")),
                    )

    def test_o_indicador_ganha_vao_so_a_direita(self) -> None:
        """**O vão é entre indicador e rótulo**, e não em volta do conjunto -- esse já é o
        `padding` da classe. Somar os dois lugares daria o dobro do pedido."""
        theme.apply_theme(self.root)
        estilo = theme.estilo_atual()
        if estilo is None:  # pragma: no cover
            self.skipTest("sem Style disponível")
        esperado = folha.vao_do_indicador(base=theme.fonte_base()[0])
        for classe in folha.COM_INDICADOR:
            with self.subTest(classe=classe):
                margem = _par(estilo.lookup(classe, "indicatormargin"))
                if margem == ():  # pragma: no cover - tema que não lê `indicatormargin`
                    self.skipTest(f"{classe} não expõe indicatormargin neste tema")
                self.assertEqual((0, 0, esperado, 0), margem)

    def test_a_aba_montada_ganha_a_folga_que_nao_tinha(self) -> None:
        """O critério de aceite da S-441, medido no widget e não no `lookup`: a faixa de abas da
        pele clássica desenhava o rótulo encostado na borda dos dois lados."""
        theme.apply_theme(self.root)
        quadro = ttk.Frame(self.root)
        self.addCleanup(quadro.destroy)
        caderno = ttk.Notebook(quadro)
        caderno.add(ttk.Frame(caderno), text="Resultado")
        caderno.pack()
        self.root.update_idletasks()
        horizontal, _vertical = folha.recheio("TNotebook.Tab", base=theme.fonte_base()[0])
        self.assertGreaterEqual(horizontal, 12, "a folga da aba encolheu abaixo do critério")
        self.assertGreater(caderno.winfo_reqheight(), 24, "a aba montada não cresceu")

    def test_a_densidade_compacta_encolhe_a_folha_no_style(self) -> None:
        theme.apply_theme(self.root, densidade=pele.COMPACTA)
        estilo = theme.estilo_atual()
        if estilo is None:  # pragma: no cover
            self.skipTest("sem Style disponível")
        compacta = _par(estilo.lookup("TNotebook.Tab", "padding"))
        theme.apply_theme(self.root, densidade=pele.CONFORTAVEL)
        confortavel = _par(estilo.lookup("TNotebook.Tab", "padding"))
        self.assertLess(compacta, confortavel)

    def test_um_tema_que_recusa_a_opcao_nao_derruba_o_resto(self) -> None:
        """O contrato de `ui/theme.py:12-15` com um dono a mais (regra 4).

        Recusar `indicatormargin` -- a única opção desta folha que não existe em todo tema `ttk`
        -- não pode custar o `padding` das outras classes.
        """
        estilo = theme.estilo_atual()
        if estilo is None:  # pragma: no cover
            self.skipTest("sem Style disponível")
        real = estilo.configure

        def recusa_o_indicador(estilo_ou_classe: object, **opcoes: object) -> object:
            if "indicatormargin" in opcoes:
                raise tk.TclError("tema sem indicatormargin")
            return real(estilo_ou_classe, **opcoes)

        with patch.object(type(estilo), "configure", side_effect=recusa_o_indicador, autospec=False):
            with self.assertLogs(folha.logger, level="INFO") as registro:
                folha.aplicar(estilo, base=9, densidade=pele.CONFORTAVEL)
        self.assertIn("indicador", "\n".join(registro.output).lower())
        self.assertEqual(folha.recheio("TNotebook.Tab", base=9), _par(estilo.lookup("TNotebook.Tab", "padding")))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
