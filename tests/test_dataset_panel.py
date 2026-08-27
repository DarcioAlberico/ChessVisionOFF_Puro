"""A aba Dataset relê quando alguém olha, e não quando alguém grava (S-116).

`Ctrl+S` avisava a aba Dataset, que chamava `load_rows` sobre o `labels.csv` inteiro **na
thread do Tk e mesmo nunca tendo sido aberta**. Medido nesta máquina sobre 3.936 linhas:

    load_rows (aba Dataset) .......   688.7 ms
    LabelStore.read() .............    29.2 ms
    saved_diagrams_by_page ........     0.2 ms
    TOTAL por Ctrl+S ..............   718.1 ms

É o laço mais interno do projeto -- corrigir, salvar, seta, corrigir --, e ele custava quase um
segundo de janela travada por amostra. O custo cresce com o arquivo que o projeto existe para
fazer crescer.

**Por que estes testes precisam de Tk.** A decisão é "esta aba está na tela?", e quem responde
isso é o `winfo_ismapped` do widget. Um teste sem Tk mediria uma variável booleana que eu mesmo
teria posto -- e não a regra. O que se dirige aqui é a resposta do `ismapped`, que é a entrada
da decisão; o resto é o painel de verdade.
"""

from __future__ import annotations

import sys
import threading
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

from tk_root import raiz as raiz_do_processo

from chess_diagram_ocr.labels import SavedSample
from chess_diagram_ocr.ui import dataset_panel as modulo
from chess_diagram_ocr.ui.busy import BusyRegistry
from chess_diagram_ocr.ui.dataset_panel import DatasetPanel


class RecargaPreguicosaTests(unittest.TestCase):
    """Uma raiz para a classe, **criada e destruída aqui** -- o molde do `test_gallery_panel`.

    Não é escolha de estilo, e o custo de errar é grande: este módulo roda cedo na ordem
    alfabética, e uma raiz que sobrevivesse a ele deixaria uma segunda viva enquanto os
    módulos seguintes criam e destroem as deles. Nesta máquina isso quebra o Tcl -- 47 testes
    de `test_gallery_panel`, `test_pdf_panel` e `test_result_panel` falharam assim, com
    `image "pyimage1" doesn't exist` e `Can't find a usable tk.tcl`, apontando para os módulos
    errados.
    """

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz_do_processo()

    def setUp(self) -> None:
        self.leituras = 0
        host = tk.Frame(self.root)
        self.addCleanup(host.destroy)

        def _load_rows(*_args: object, **_kwargs: object) -> list[object]:
            self.leituras += 1
            return []

        remendo = mock.patch.object(modulo, "load_rows", _load_rows)
        remendo.start()
        self.addCleanup(remendo.stop)

        self.painel = DatasetPanel(
            host,
            paths=lambda: (Path("labels.csv"), Path("samples"), Path("splits.csv")),
            on_edit=lambda _linha: None,
            on_status=lambda _texto: None,
        )
        # A raiz do teste e `withdraw()`, entao nada abaixo dela e mapeado de verdade. O que
        # se dirige e a resposta do `ismapped`, que e a entrada da decisao.
        self._visivel = False
        self.painel.winfo_ismapped = lambda: self._visivel  # type: ignore[method-assign]

    def test_gravar_com_a_aba_fechada_nao_le_o_arquivo(self) -> None:
        """**O item numa linha.** Quem nunca abre a aba Dataset nunca paga os 689 ms."""
        self.painel.reload()
        self.painel.reload()
        self.painel.reload()

        self.assertEqual(self.leituras, 0)

    def test_abrir_a_aba_depois_de_gravar_le_uma_vez_so(self) -> None:
        """Três gravações escondidas não viram três leituras: o estado é "mudou", não "quantas"."""
        self.painel.reload()
        self.painel.reload()
        self.painel.reload()

        self._visivel = True
        self.painel._on_map()

        self.assertEqual(self.leituras, 1)

    def test_abrir_a_aba_sem_nada_ter_mudado_nao_le_de_novo(self) -> None:
        """Trocar de aba ida e volta é gesto de navegação, e não pode custar 689 ms cada."""
        self._visivel = True
        self.painel._on_map()
        self.assertEqual(self.leituras, 1, "a primeira vez sempre lê: a aba nasce sem linha nenhuma")

        self.painel._on_map()
        self.painel._on_map()

        self.assertEqual(self.leituras, 1)

    def test_com_a_aba_aberta_gravar_continua_recarregando_na_hora(self) -> None:
        """A preguiça é sobre quem não está olhando. Quem está, vê a amostra nova aparecer."""
        self._visivel = True
        self.painel._on_map()

        self.painel.reload()

        self.assertEqual(self.leituras, 2)

    def test_o_botao_recarregar_continua_lendo(self) -> None:
        """Ele existe justamente para quem mexeu no `labels.csv` por fora."""
        self._visivel = True
        self.painel.reload()
        self.assertEqual(self.leituras, 1)

    def test_o_painel_escuta_o_proprio_map(self) -> None:
        """Sem este vínculo a preguiça vira esquecimento: a aba abriria com a tabela velha.

        O `ttk.Notebook` mapeia e desmapeia o quadro de cada aba ao trocar de aba, e é por isso
        que o sinal chega ao painel sem que a janela principal precise saber de nada.
        """
        self.assertTrue(self.painel.bind("<Map>"), "o painel precisa escutar <Map>")


if __name__ == "__main__":
    unittest.main()


class _VarFalsa:
    """O bastante de uma `tk.StringVar` para a janela mínima ler o caminho do CSV."""

    def __init__(self, valor: str) -> None:
        self._valor = valor

    def get(self) -> str:
        return self._valor


def _janela_minima(app_tkinter):  # noqa: ANN001, ANN202
    """A janela reduzida ao que o aviso de "amostra gravada" toca, com os métodos reais.

    Mesmo recurso do `test_packaging._janela_minima`: montar o `ChessOcrTkApp` inteiro exigiria
    checkpoint e PDF, e o que se testa aqui é o que este caminho **deixou de ler**.
    """
    tipo = type(
        "JanelaMinima",
        (),
        {
            "_reload_dataset_panel": app_tkinter.ChessOcrTkApp._reload_dataset_panel,
            "_reload_saved_diagrams": app_tkinter.ChessOcrTkApp._reload_saved_diagrams,
            "_pdf_name": app_tkinter.ChessOcrTkApp._pdf_name,
            "_read_confirmed": app_tkinter.ChessOcrTkApp._read_confirmed,
            "_refresh_overlay": lambda self, _pagina: self.repintadas.append(_pagina),
            "_atualizar_abas": lambda self: None,
        },
    )
    janela = tipo()
    janela.dataset_panel = None
    janela.saved_diagrams = {}
    janela.confirmed_diagrams = {}
    janela.pdf_source = Path("Karpov 1.pdf")
    janela.dataset_csv_var = _VarFalsa("labels.csv")
    janela.page_index = 15
    janela.repintadas = []
    return janela


class CorteDoisTests(unittest.TestCase):
    """O que o `Ctrl+S` deixou de ler: o `labels.csv` e as anotações do livro (S-116, corte 2).

    Feito o corte 1, sobravam **46,1 ms** por amostra salva, e 45,9 deles eram duas leituras de
    disco para descobrir o que este mesmo processo acabara de escrever:

        LabelStore.read() .............    30,9 ms   <- cresce com o labels.csv
        load_annotations (do livro) ...    15,0 ms
        saved_diagrams_by_page ........     0,2 ms

    O que substituiu as duas é o próprio dado da gravação, que agora atravessa o
    `on_sample_saved` em vez de ser redescoberto.
    """

    @staticmethod
    def _app_tkinter():  # noqa: ANN205
        """`app_tkinter.py` mora na raiz e não é pacote; o pytest só põe `src/` no path."""
        raiz = str(Path(__file__).resolve().parents[1])
        if raiz not in sys.path:
            sys.path.insert(0, raiz)
        import app_tkinter

        return app_tkinter

    def setUp(self) -> None:
        self.app_tkinter = self._app_tkinter()
        self.janela = _janela_minima(self.app_tkinter)
        self.leituras: list[str] = []

        def _espiao(nome: str, resposta: object):  # noqa: ANN202
            def _chamada(*_args: object, **_kwargs: object) -> object:
                self.leituras.append(nome)
                return resposta
            return _chamada

        vazio = mock.Mock(entries={})
        for nome, resposta in (
            ("LabelStore", mock.Mock(read=_espiao("LabelStore.read", []))),
            ("saved_diagrams_by_page", {}),
            ("load_annotations", vazio),
        ):
            remendo = mock.patch.object(self.app_tkinter, nome, _espiao(nome, resposta))
            remendo.start()
            self.addCleanup(remendo.stop)

    def test_salvar_uma_amostra_nao_le_arquivo_nenhum(self) -> None:
        """**O item numa linha.** O que ficou verde foi o que a janela acabou de gravar."""
        gravada = SavedSample(source_pdf="Karpov 1.pdf", page_index=15, diagram_index=2)

        self.janela._reload_dataset_panel([gravada])

        self.assertEqual(self.leituras, [], "nenhuma leitura de disco no laço mais interno")
        self.assertEqual(self.janela.saved_diagrams, {15: {2}})
        self.assertEqual(self.janela.repintadas, [15], "e a página é repintada uma vez")

    def test_salvar_todos_marca_os_quatro_sem_ler_quatro_vezes(self) -> None:
        gravadas = [SavedSample("Karpov 1.pdf", 15, n) for n in range(4)]

        self.janela._reload_dataset_panel(gravadas)

        self.assertEqual(self.leituras, [])
        self.assertEqual(self.janela.saved_diagrams, {15: {0, 1, 2, 3}})

    def test_regravar_uma_linha_nao_inventa_diagrama_verde(self) -> None:
        """Regravar o rótulo de uma amostra que já existia não muda o que está salvo -- e a
        sequência vazia é como o editor diz isso."""
        self.janela._reload_dataset_panel(())

        self.assertEqual(self.leituras, [])
        self.assertEqual(self.janela.saved_diagrams, {})

    def test_amostra_de_outro_livro_nao_pinta_o_livro_aberto(self) -> None:
        """A defesa é do índice, e não de quem chama: ele é do PDF que está na tela."""
        self.janela._reload_dataset_panel([SavedSample("Outro.pdf", 15, 2)])

        self.assertEqual(self.janela.saved_diagrams, {})

    def test_abrir_um_livro_continua_lendo_o_arquivo(self) -> None:
        """A releitura não sumiu: ela mudou de gatilho. Abrir um PDF é quando ela vale, porque
        aí o índice não existe -- e é uma vez por livro, não uma por amostra."""
        self.janela._reload_saved_diagrams(Path("Karpov 1.pdf"))

        self.assertIn("LabelStore", self.leituras)
        self.assertIn("load_annotations", self.leituras)


class UmaDeteccaoDeCadaVezTests(unittest.TestCase):
    """O segundo clique em "Detectar duplicatas" não vaza um registro de operação longa (S-314).

    **O dano ficava na sessão seguinte.** `detect_duplicates` sobrescrevia `_busy_token` a cada
    clique, e `_release_busy` só solta a chave que está no atributo -- a do primeiro clique
    ficava registrada para sempre. `BusyRegistry.running()` não filtra por `loses_work`, então a
    chave vazada entra na pergunta de fechamento: a janela passa a avisar que há uma operação em
    andamento que terminou há horas, que é exatamente o que essa pergunta existe para não fazer.
    """

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz_do_processo()

    def setUp(self) -> None:
        host = tk.Frame(self.root)
        self.addCleanup(host.destroy)
        self.registro = BusyRegistry()
        self.frases: list[str] = []
        remendo = mock.patch.object(modulo, "load_rows", lambda *_a, **_k: [])
        remendo.start()
        self.addCleanup(remendo.stop)
        # A detecção nunca termina: é o estado que o segundo clique encontra.
        self._solta = threading.Event()
        self.addCleanup(self._solta.set)
        parada = mock.patch.object(
            modulo, "find_duplicate_groups", lambda *_a, **_k: (self._solta.wait(), [])[1]
        )
        parada.start()
        self.addCleanup(parada.stop)
        self.painel = DatasetPanel(
            host,
            paths=lambda: (Path("labels.csv"), Path("samples"), Path("splits.csv")),
            on_edit=lambda _linha: None,
            on_status=self.frases.append,
            busy=self.registro,
        )

    def test_o_segundo_clique_nao_registra_uma_segunda_operacao(self) -> None:
        self.painel.detect_duplicates()
        self.painel.detect_duplicates()
        self.painel.detect_duplicates()

        self.assertEqual(len(self.registro.running()), 1)
        self.assertTrue(any("já está em andamento" in frase for frase in self.frases), self.frases)

    def test_o_botao_fica_cinza_enquanto_ela_roda(self) -> None:
        """O botão cinza é a mesma resposta da frase, e não depende de a pessoa estar olhando."""
        self.assertEqual(str(self.painel.btn_duplicatas.cget("state")), "normal")

        self.painel.detect_duplicates()

        self.assertEqual(str(self.painel.btn_duplicatas.cget("state")), "disabled")


if __name__ == "__main__":
    unittest.main()
