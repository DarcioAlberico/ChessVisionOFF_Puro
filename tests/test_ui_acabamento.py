"""Acabamento é da janela, e não da pele (S-443).

**O que este arquivo substitui.** A regra 1 da `SPEC_APARENCIA.md` dizia *"a pele clássica é o
padrão e não muda"*, e ela protegia contra uma coisa real: que a clássica ganhasse controle em
lugar diferente e virasse uma quarta tela a manter. Só que "não muda" fundia dois eixos, e o preço
apareceu na S-441: o `padding=(14, 6)` da faixa de abas existia desde a S-226 e era entregue **a
uma pele só**, porque melhorá-lo na clássica era proibido. A faixa da pele padrão desenhava o
rótulo encostado na borda dos dois lados, e não havia caminho para consertar.

A regra passa a separar os dois eixos:

- **arranjo** -- quais controles existem, onde ficam, em que ordem. Continua congelado na clássica,
  e quem o cobra é `test_ui_alcance.py` (S-233), por inventário;
- **acabamento** -- folga, peso, alinhamento, indicador. **Não é da pele.** Chega às três ao mesmo
  tempo, ou não chega a nenhuma. É o que este arquivo cobra.

**A densidade não é acabamento**, e é a distinção que o teste precisa acertar: a pele "Fita" sugere
compacta, e uma folha compacta é *menor* de propósito. O que tem de ser igual é o acabamento **na
mesma densidade** -- é o eixo da S-232, e ele continua sendo escolha da pessoa.
"""

from __future__ import annotations

import tkinter as tk
import unittest

from test_ui_folha import _par
from tk_root import raiz

from chess_diagram_ocr.ui import folha, pele, theme

OBSERVADAS: tuple[str, ...] = (
    "TButton",
    "TNotebook.Tab",
    "TCheckbutton",
    "TEntry",
    "TSpinbox",
    "TLabelframe",
)
"""As classes que o critério de aceite da S-443 nomeia, mais as duas que a folha acrescentou.

**Duas delas -- `TButton` e `TEntry` -- não estão na folha de propósito**, e é por isso que elas
entram aqui: o acabamento tem de ser o mesmo nas três peles *inclusive* onde quem o decide é o
tema. Se um dia alguém der ao `TButton` um valor por pele, é este teste que reprova.
"""


class MesmoAcabamentoNasTresPelesTests(unittest.TestCase):
    """O teste que substitui a proteção que a regra 1 dava."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.addCleanup(lambda: theme.apply_theme(self.root, densidade=pele.CONFORTAVEL))

    def _acabamento(self, registro: pele.Pele, densidade: str) -> dict[str, tuple[int, ...]]:
        """O `padding` resolvido de cada classe, com a pele aplicada como a janela a aplica."""
        theme.apply_theme(self.root, cromo_escuro=registro.cromo_escuro, densidade=densidade)
        estilo = theme.estilo_atual()
        if estilo is None:  # pragma: no cover - sem ttk não há acabamento a conferir
            self.skipTest("sem Style disponível")
        return {classe: _par(estilo.lookup(classe, "padding")) for classe in OBSERVADAS}

    def test_as_tres_peles_recebem_o_mesmo_acabamento(self) -> None:
        """**O item.** Antes da S-441 este teste reprovaria em `TNotebook.Tab`: a clássica e a
        "Fita" liam `''` e a "Foco" lia `14 6`."""
        for densidade in pele.DENSIDADES:
            medidas = {registro.nome: self._acabamento(registro, densidade) for registro in pele.PELES}
            referencia = medidas[pele.CLASSICA]
            for nome, medida in medidas.items():
                with self.subTest(pele=nome, densidade=densidade):
                    self.assertEqual(referencia, medida, "o acabamento mudou com a pele")

    def test_a_faixa_discreta_difere_em_peso_e_nao_em_folga(self) -> None:
        """A pele "Foco" continua tendo a faixa dela (S-226) -- e o que ela tem de próprio é
        `borderwidth=0`. A folga vem da folha, herdada pelo prefixo do nome de estilo.

        É a fronteira que a S-441 desenhou ao tirar o `padding` de `Discreta.TNotebook.Tab`: se
        alguém o devolver para lá, a folga volta a ser de uma pele só, e é aqui que isso reprova.
        """
        theme.apply_theme(self.root)
        estilo = theme.estilo_atual()
        if estilo is None:  # pragma: no cover
            self.skipTest("sem Style disponível")
        discreta = f"{theme.ESTILO_DE_ABAS_DISCRETO}.Tab"
        self.assertEqual(
            _par(estilo.lookup("TNotebook.Tab", "padding")),
            _par(estilo.lookup(discreta, "padding")),
        )
        self.assertEqual(0, int(str(estilo.lookup(discreta, "borderwidth"))))

    def test_a_densidade_continua_podendo_mudar_o_acabamento(self) -> None:
        """**A metade do critério que uma implementação apressada troca por "tudo igual".**

        Pele não muda acabamento; densidade muda, e é para isso que ela existe. Um teste que
        exigisse igualdade entre densidades estaria cobrando o contrário da S-232.
        """
        classica = pele.registrada(pele.CLASSICA)
        compacta = self._acabamento(classica, pele.COMPACTA)
        confortavel = self._acabamento(classica, pele.CONFORTAVEL)
        self.assertLess(compacta["TNotebook.Tab"], confortavel["TNotebook.Tab"])

    def test_toda_pele_registrada_entra_na_conta(self) -> None:
        """Uma pele nova registrada sem passar por aqui é o defeito que a S-233 já preveniu para
        alcance. O mesmo argumento vale para acabamento."""
        self.assertEqual({pele.CLASSICA, pele.FOCO, pele.FITA}, {p.nome for p in pele.PELES})
        for classe in folha.CLASSES:
            with self.subTest(classe=classe):
                self.assertIn(classe, OBSERVADAS + ("TRadiobutton",))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
