"""O que muda quando o programa é um `.exe` em vez de um checkout (S-55).

Um único defeito de empacotamento é caro de um jeito diferente dos outros: ele só aparece
na máquina de outra pessoa, e o sintoma é uma janela que some. Estes testes cobrem a parte
que **pode** ser verificada aqui — para onde o programa aponta quando `sys.frozen` está
posto — e o resto o `--selftest` responde na máquina de destino.
"""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJETO = Path(__file__).resolve().parents[1]


class FrozenRootTests(unittest.TestCase):
    """`data/`, `models/`, `PDF/` e `PGN/` ficam **ao lado** do executável, não dentro dele."""

    def _config_congelado(self, executavel: str, meipass: str | None):
        """Reimporta `config` fingindo um bundle. É a única forma de exercitar o ramo."""
        import chess_diagram_ocr.config as config

        patches = {"frozen": True, "executable": executavel}
        if meipass is not None:
            patches["_MEIPASS"] = meipass
        with patch.multiple(sys, create=True, **patches):
            return importlib.reload(config)

    def tearDown(self) -> None:
        # Sem isto o modulo fica com a raiz falsa para todo teste que rodar depois.
        import chess_diagram_ocr.config as config

        importlib.reload(config)

    def test_a_raiz_gravavel_e_a_pasta_do_executavel(self) -> None:
        """O `labels.csv` é trabalho humano acumulado: dentro do bundle, reinstalar o apaga."""
        pasta = Path(PROJETO / "dist" / "ChessVisionOFF")
        config = self._config_congelado(str(pasta / "ChessVisionOFF.exe"), str(pasta / "_internal"))

        self.assertEqual(config.PROJECT_ROOT, pasta)
        self.assertEqual(config.DEFAULT_DATASET_CSV, pasta / "data" / "labels.csv")
        self.assertEqual(config.DEFAULT_MODEL_PATH, pasta / "models" / "piece_classifier.pt")
        self.assertEqual(config.DEFAULT_PDF_DIR, pasta / "PDF")

    def test_os_recursos_do_programa_ficam_dentro_do_bundle(self) -> None:
        """Imagem de peça é dado do programa; rótulo é dado do usuário. Não é o mesmo lugar."""
        pasta = Path(PROJETO / "dist" / "ChessVisionOFF")
        config = self._config_congelado(str(pasta / "ChessVisionOFF.exe"), str(pasta / "_internal"))

        self.assertEqual(config.BUNDLE_ROOT, pasta / "_internal")
        self.assertNotEqual(config.BUNDLE_ROOT, config.PROJECT_ROOT)

    def test_num_checkout_as_duas_raizes_coincidem(self) -> None:
        import chess_diagram_ocr.config as config

        self.assertEqual(config.PROJECT_ROOT, PROJETO)
        self.assertEqual(config.BUNDLE_ROOT, PROJETO)


class FrozenLogFileTests(unittest.TestCase):
    """Congelado, o programa tem para onde escrever quando algo falha (S-127).

    O `console=False` da spec troca o terminal pelo arquivo. Enquanto `default_log_file()`
    devolvia `None` sem `CVOFF_LOG_DIR` -- e nada no bundle a definia --, a troca era por nada:
    uma janela que não abria não deixava rastro em lugar nenhum.
    """

    PASTA = PROJETO / "dist" / "ChessVisionOFF"

    def setUp(self) -> None:
        import chess_diagram_ocr.config as config

        self.config = config
        # `CVOFF_LOG_DIR` do ambiente de quem roda a suite mascararia o ramo congelado.
        self.env = patch.dict("os.environ", {}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        import os

        os.environ.pop("CVOFF_LOG_DIR", None)
        # Sem isto o modulo fica com a raiz falsa para todo teste que rodar depois.
        self.addCleanup(importlib.reload, config)

    def _congelado(self):
        patches = {
            "frozen": True,
            "executable": str(self.PASTA / "ChessVisionOFF.exe"),
            "_MEIPASS": str(self.PASTA / "_internal"),
        }
        return patch.multiple(sys, create=True, **patches)

    def test_congelado_o_log_fica_ao_lado_do_executavel(self) -> None:
        from chess_diagram_ocr.logging_setup import default_log_file

        with self._congelado():
            importlib.reload(self.config)
            self.assertEqual(default_log_file(), self.PASTA / "logs" / "chessvisionoff.log")

    def test_o_log_nao_vai_para_dentro_do_bundle(self) -> None:
        """`_MEIPASS` some a cada reinstalação — a pior propriedade para um rastro de falha."""
        from chess_diagram_ocr.logging_setup import default_log_file

        with self._congelado():
            importlib.reload(self.config)
            caminho = default_log_file()

        assert caminho is not None
        self.assertNotIn("_internal", caminho.parts)

    def test_num_checkout_continua_sem_arquivo_sem_pedir(self) -> None:
        """O terminal já é o rastro. Um `.log` que ninguém pediu só suja o repositório."""
        from chess_diagram_ocr.logging_setup import default_log_file

        self.assertIsNone(default_log_file())

    def test_a_variavel_de_ambiente_continua_mandando(self) -> None:
        from chess_diagram_ocr.logging_setup import default_log_file

        with patch.dict("os.environ", {"CVOFF_LOG_DIR": str(PROJETO / "outro")}):
            with self._congelado():
                importlib.reload(self.config)
                self.assertEqual(default_log_file(), PROJETO / "outro" / "chessvisionoff.log")

    def test_a_pasta_de_log_nasce_junto_com_as_do_usuario(self) -> None:
        """Uma pasta que só existe depois do problema é uma instrução que não se pode seguir."""
        if str(PROJETO / "packaging") not in sys.path:
            sys.path.insert(0, str(PROJETO / "packaging"))
        import build_windows

        self.assertIn("logs", build_windows.PASTAS_DO_USUARIO)

    def test_a_janela_que_nao_abre_deixa_o_traceback_no_log(self) -> None:
        """É o `logger.exception` de `main` que enche o arquivo: `stderr` num bundle
        `console=False` não vai a lugar nenhum, e é a única falha que ninguém diagnostica."""
        app_tkinter = SelftestTests._app_tkinter()

        with patch.object(app_tkinter, "ChessOcrTkApp", side_effect=RuntimeError("Tcl morreu")):
            with patch.object(app_tkinter.tk, "Tk", lambda: None):
                with patch.object(sys, "argv", ["app_tkinter.py"]):
                    with self.assertLogs(app_tkinter.logger, level="ERROR") as registro:
                        with self.assertRaises(RuntimeError):
                            app_tkinter.main()

        self.assertIn("Traceback", registro.output[0])
        self.assertIn("Tcl morreu", registro.output[0])


class TamanhoDaJanelaTests(unittest.TestCase):
    """`app_tkinter.py` não volta a crescer sem alguém decidir (S-136).

    **O número original era 600**, e é o critério de aceite da S-31 (`SPEC.md`). Ele não é
    arbitrário: a S-31 quebrou uma janela de 2.388 linhas porque "o que dá para testar não fica
    na janela", e 600 era onde o que sobrava era layout puro. Fechou em **651**, com a decisão
    escrita de que os ~50 restantes não valiam a pena — o que era honesto a 651.

    Hoje são **1.440**: 2.388 → 651 → 703 → 1.153 → 1.302 → 1.440. O arquivo **dobrou depois da
    decomposição** e nenhum documento registrava. O custo tem nome: a S-95 — a decisão de onde
    vem a verdade de referência do conjunto de campo mora nessas linhas, gravou a leitura do
    próprio modelo por três meses, e não tinha teste porque não dava para testar sem janela.

    **Este teste é uma catraca, não uma meta.** O corte é o valor de hoje. Baixá-lo é a S-31
    reaberta; subi-lo exige vir aqui e editar o número, que é o ponto: passa a ser uma decisão
    em vez de um acidente, que é o que o `CONTRIBUTING.md` pede de um teste.

    Registrar em vez de extrair foi escolha de data e não de princípio — há uma avaliação de
    interface em curso (`docs/ROADMAP_UI.md`) que vai reorganizar este arquivo, e decidir a
    decomposição antes de lê-la seria colidir com ela.
    """

    LIMITE = 1800
    """Linhas de `app_tkinter.py`. Ver o docstring da classe antes de mudar.

    **1.788 → 1.800 na S-211**, e as 12 são a aba de texto entrando. Nenhuma delas decide nada: o
    `import`, o campo do painel, a chamada do construtor com seis argumentos -- os mesmos seis que
    as outras abas recebem -- e o `tabs.add`. **O que dava para extrair já nasceu extraído**: a aba
    inteira é `ui/texto_panel.py`, e o que ela decide (onde o diagrama entra no texto, o que merece
    destaque, o que vai para o arquivo) é `text/documento.py`, que não importa `tkinter`. Até o
    comentário que explicava a **posição** da aba na barra saiu daqui para o docstring do painel,
    que é onde ele continua verdadeiro se alguém reordenar as abas.


    **1.440 → 1.457 em 2026-08-17**, e a catraca funcionou: ela pegou o próprio crescimento.
    As 17 linhas são da S-144 (o botão "Anotar página" quebrado em cinco linhas para receber
    `style=`) e da S-150 (as duas constantes de largura mínima, com docstring, e a chamada de
    `minsize`). Nenhuma é lógica nova -- são as que a Fase 20 precisava pôr aqui.

    **1.457 → 1.461 na S-148**, e as quatro são as menores que o item admite: duas chamadas de
    `ui/plataforma.py` e o comentário de duas linhas que explica **por que uma vem antes de
    `tk.Tk()`** — que é a decisão inteira do item, e a que se perde primeiro se ninguém a
    escrever aqui. A lógica de DPI e ícone toda mora no módulo novo; o que ficou nesta janela é
    a ordem, e ordem não dá para extrair.

    **1.461 → 1.500 na S-156**, e este é o maior salto desde que a catraca existe. O item é
    "lembrar o arranjo da janela", e arranjo de janela é, por definição, do objeto que **é** a
    janela: a geometria do `root`, a alça do `PanedWindow` e a aba selecionada do `Notebook` não
    existem em lugar nenhum de `ui/`.

    O que dava para extrair foi extraído, e é a maior parte do item: `geometria_de_texto`,
    `geometria_corrigida`, `geometria_a_aplicar`, `geometria_gravavel`, `visivel_em` e
    `fracao_de_divisor` em `ui/geometria.py`, `monitores` em `ui/plataforma.py`, `selecionar_aba`
    em `ui/rolagem.py`, e os três campos em `ui/state.py` -- **nove funções puras contra as 39
    linhas que sobraram aqui**, e as 39 são leitura e escrita de widget, sem decisão nenhuma.

    **1.500 → 1.501 na S-154**, e a linha é a frase que diz por que `LARGURA_MINIMA_ESQUERDA`
    deixou de ser 420. O número em si **encolheu** de responsabilidade: era cravado aqui e agora
    deriva de `gallery_panel.LARGURA_MINIMA_DA_GALERIA`.

    **1.501 → 1.525 na S-167 + S-168**, e as 24 são de duas naturezas. A S-167 põe
    `_atualizar_titulo` -- nove linhas que leem o painel de PDF e chamam
    `strings.titulo_da_janela`; a decisão inteira (o corte pelo meio, a página fora de faixa) é
    de `ui/strings.py`. A S-168 troca `_entry_row` -- que **saiu daqui**, com as cinco linhas
    dele -- por `ui/campos.py`, e deixa `_train_lr`, que é a conversão do texto do campo em
    número. Nenhuma das duas decide nada: quem decide se um caminho existe, se um texto é
    número e onde o nome do livro é cortado são funções puras dos módulos de `ui/`.

    **1.525 → 1.533 na S-163**, e as oito são o rodapé entrando e a barra de status saindo. O
    saldo é enganosamente pequeno: o `ttk.Label` do painel esquerdo saiu (−1), e o que entrou são
    quatro linhas de construção e empacotamento -- as três zonas, a severidade, a expiração e a
    projeção do `BusyRegistry` moram em `ui/rodape.py`, com 11 funções puras. O que ficou aqui é
    **a ordem do `pack`**: o rodapé antes do `PanedWindow`. Ordem de empacotamento é do objeto
    que é a janela, e não dá para extrair -- é a mesma razão da S-148 e da S-156.

    **1.533 → 1.536 na S-164**, e as três são as duas linhas de comentário que dizem por que o
    "nenhum diagrama nesta página" deixou de abrir caixa e a frase que junta a dica à mensagem. O
    item inteiro -- progresso numérico no registro, projeção para a barra, 22 caixas convertidas --
    aconteceu em `ui/busy.py`, `ui/rodape.py` e nos seis painéis; aqui só passou o que o
    `_on_ocr_empty` desta janela dizia.

    **1.536 → 1.595 na S-161**, e é o maior salto desde que a catraca existe -- maior que o da
    S-156. Cinquenta e nove linhas, e 30 delas são **uma tabela**: `_comandos`, o mapa de 26 nomes
    de comando para os métodos desta janela. Ela não decide nada; ela amarra. Quem declara **qual
    tecla** faz o quê é `ui/atalhos.py` (10 linhas de tabela, sem `tkinter`), e quem declara **onde
    cada comando aparece** é `ui/menu.py` (cinco menus, também sem widget). O que não dá para tirar
    daqui é a amarração em si: só este objeto tem os painéis.

    As 29 restantes são `_build_menu` (7), `_livros_recentes` (3), `_abrir_log` (11, com o caso de
    não haver log num checkout) e `_sobre` (3), menos o dicionário literal de atalhos que **saiu**
    (`_bind_shortcuts` tinha 18 linhas e tem 3). Contra isso, a janela ganhou 26 comandos
    alcançáveis por menu e os 10 atalhos escritos num lugar onde alguém os encontra.

    **1.595 → 1.597 na S-165**, e as duas são o import de `ui/legenda.py` e a linha que amarra o
    item "Atalhos de teclado" do menu Ajuda à janela dela. A legenda inteira -- as dez linhas, a
    tipografia monoespaçada da tecla, a nota sobre a guarda de foco -- é do módulo novo, e ela se
    escreve sozinha: percorre `ATALHOS`.

    **1.597 → 1.606 na S-165 (2ª metade)**, e as nove são o tooltip do "Treinar modelo" -- o único
    controle desabilitável que mora nesta janela -- mais `_abrir_legenda`. O motivo escrito é o
    conteúdo do item: sem ele, o botão fica cinza durante o treino e não diz que é por isso.

    **1.606 → 1.642 na S-162**, e as 32 são quase todas `_atualizar_abas`: as contagens das três
    abas que têm uma, lidas dos painéis que as guardam, mais os comentários que explicam por que a
    atualização acontece em três pontos e não num relógio. As outras oito são o
    `enable_traversal()`, a aba inicial e o comentário da nova ordem das abas. A decisão -- o que
    o rótulo mostra, o zero que não vira "(0)", o milhar em pt-BR, o nome sem a contagem -- é de
    `ui/abas.py`, com teste próprio.

    **1.642 → 1.646 na S-119**, e as quatro são a ligação entre as duas abas que passaram a
    dividir uma varredura: `review_sink` na Galeria, `on_scan_book` e `on_cancel_book` na
    Revisão -- mais um comando do menu que **saiu**, porque virou o mesmo gesto do outro. É o
    tipo de linha que só pode morar aqui: nenhuma das duas abas conhece a outra, e quem as liga
    é a janela.

    **1.646 → 1.677 na S-116 (corte 2)**, e as 31 são de dois tipos. `_reload_dataset_panel`
    passou a receber o que foi gravado e a marcá-lo (a aritmética é de `labels.note_saved_diagram`,
    com teste sem janela); e `_reload_confirmed_diagrams` nasceu porque o violeta das caixas
    vinha de carona no `Ctrl+S` — que agora não lê mais nada. As duas são leitura e escrita de
    estado da janela, que é o que não dá para extrair. O que **saiu** desta janela foram 65 ms
    por amostra salva.

    **1.677 → 1.712 na Fase 18**. e elas são as duas guardas do `--selftest` mais o comentário
    que diz por que existem: exercitar o `.exe` recém-construído mostrou que um `.pt` truncado e
    um PDF corrompido saíam os dois com **1 e um traceback em inglês**. onde 1 quer dizer "o
    programa falhou" e quem falhou era um arquivo. Carregar o modelo e abrir o PDF viraram passos
    próprios -- e passo próprio é o que dá para classificar.

    **1.712 → 1.776 na S-177**, e o que ficou aqui é o mínimo do gesto de tirar uma caixa da
    página. O que **saiu**: a regra da remoção é `page_overlay.DroppedBoxes` (casar caixa com
    caixa por IoU, não renumerar o que sobra, ser por página e por livro), as duas frases da
    barra de status são `page_overlay.frase_de_caixa_tirada` e `frase_de_caixas_devolvidas`, e o
    gesto -- botão, botão direito, ausência de seleção -- é `pdf_panel`. O que sobrou são
    `_drop_box` e `restore_dropped_boxes`, que leem o painel, escrevem no registro da sessão e
    mandam repintar: as três coisas que **são** a janela, pela mesma razão que
    `_reload_dataset_panel` ficou na S-116.

    **1.776 → 1.788 na Etapa 1 do `PLANO_OCR_TEXTO`**, e as 12 são o segundo modelo torch da
    janela (S-182). O que **saiu**: a pergunta inteira -- em que dispositivo cada modelo está,
    e por que às vezes não há classificador de caracteres -- é `ui/dispositivos.py`, e o texto
    que o rodapé mostra é `ui/rodape.descricao_dos_dispositivos`. O que ficou são três linhas de
    `acompanhar`, um `import` e a linha do `--selftest` que diz se o `.pt` de caracteres veio
    junto: ler o serviço e a configuração desta janela é o que **é** a janela, pela mesma razão
    que `_reload_dataset_panel` ficou na S-116.

    Subir o número é o gesto que o teste existe para exigir: ele não impede crescer, impede
    crescer **sem decidir**."""

    ALVO_ORIGINAL = 600
    """O critério de aceite da S-31, em `docs/SPEC.md`. Fica aqui para não se perder."""

    def _linhas(self) -> int:
        return len((PROJETO / "app_tkinter.py").read_text(encoding="utf-8").splitlines())

    def test_a_janela_nao_volta_a_crescer(self) -> None:
        atual = self._linhas()
        self.assertLessEqual(
            atual,
            self.LIMITE,
            f"`app_tkinter.py` passou de {self.LIMITE} para {atual} linhas. O alvo da S-31 é "
            f"{self.ALVO_ORIGINAL}; se o crescimento for deliberado, baixe o que for possível "
            "para `ui/` ou registre o novo placar aqui e no ROADMAP, com o motivo.",
        )

    def test_o_limite_registrado_nao_esta_defasado_para_baixo(self) -> None:
        """Uma catraca que não aperta não é catraca: se o arquivo encolheu, o corte desce junto.

        Sem isto, extrair 400 linhas para `ui/` deixaria a folga de volta e o próximo
        crescimento passaria sem ninguém ver.
        """
        atual = self._linhas()
        self.assertGreater(
            atual + 40,
            self.LIMITE,
            f"`app_tkinter.py` caiu para {atual} linhas e o corte ainda é {self.LIMITE}. "
            "Baixe `LIMITE` para o novo valor.",
        )

    def test_o_alvo_original_continua_escrito_na_spec(self) -> None:
        """Se a S-31 for reaberta, é este número que ela persegue -- e ele não pode sumir."""
        spec = (PROJETO / "docs" / "SPEC.md").read_text(encoding="utf-8")
        self.assertIn(f"abaixo de {self.ALVO_ORIGINAL} linhas", spec)


class SpecTests(unittest.TestCase):
    """A spec é código que ninguém importa; sem teste, ela apodrece em silêncio."""

    def setUp(self) -> None:
        self.spec = PROJETO / "packaging" / "cvoff.spec"
        if not self.spec.exists():
            self.skipTest("packaging/cvoff.spec não existe neste checkout")
        self.texto = self.spec.read_text(encoding="utf-8")

    def test_o_ponto_de_entrada_e_a_janela(self) -> None:
        self.assertIn("app_tkinter.py", self.texto)

    def test_o_streamlit_nao_entra_no_bundle(self) -> None:
        """Desde a S-54 ele é exemplo. Empacotar um servidor web num app de desktop, não."""
        excludes = self.texto.split("excludes = [", 1)[1].split("]", 1)[0]
        self.assertIn('"streamlit"', excludes)

    def test_os_dados_do_usuario_nao_viajam_dentro_do_pacote(self) -> None:
        datas = self.texto.split("datas = [", 1)[1].split("]", 1)[0]
        for pasta in ("data", "models", "PDF", "PGN"):
            with self.subTest(pasta=pasta):
                self.assertNotIn(f'"{pasta}"', datas)

    def test_o_comentario_do_console_desligado_nomeia_o_arquivo_que_existe(self) -> None:
        """O comentário já esteve aqui sem ser verdade (S-127). Travá-lo é o que impede repetir."""
        self.assertIn("console=False", self.texto)
        self.assertIn("logs/chessvisionoff.log", self.texto)

    def test_o_modo_e_onedir(self) -> None:
        """`--onefile` extrairia ~700 MB para o temp a cada execução."""
        self.assertIn("COLLECT(", self.texto)
        self.assertIn("exclude_binaries=True", self.texto)


class SelftestTests(unittest.TestCase):
    """O `--selftest` é o que responde "esta instalação funciona?" numa máquina limpa."""

    @staticmethod
    def _app_tkinter():
        """`app_tkinter.py` mora na raiz e não é pacote; o pytest só põe `src/` no path."""
        if str(PROJETO) not in sys.path:
            sys.path.insert(0, str(PROJETO))
        import app_tkinter

        return app_tkinter

    def test_sem_checkpoint_o_codigo_de_saida_diz_o_que_falta(self) -> None:
        app_tkinter = self._app_tkinter()
        with patch.object(app_tkinter, "DEFAULT_MODEL_PATH", Path("nao/existe.pt")):
            self.assertEqual(app_tkinter.selftest(pdf=Path("qualquer.pdf")), 3)

    def test_sem_pdf_o_codigo_de_saida_e_outro(self) -> None:
        """Códigos distintos porque as duas faltas pedem ações distintas do usuário."""
        app_tkinter = self._app_tkinter()
        with patch.object(app_tkinter, "find_default_pdf_path", lambda: None):
            self.assertEqual(app_tkinter.selftest(), 2)

    def test_checkpoint_ilegivel_e_3_e_nao_1(self) -> None:
        """**Uma das três falhas que o critério da Fase 18 nomeia**, e ela não estava tratada.

        Exercitada no `.exe` recém-construído em 2026-08-18: um `.pt` truncado -- ou de outra
        `arch_version` -- caía no `except` genérico do reconhecimento e saía com **1 e um
        traceback do `torch` em inglês**, onde o README promete 3 e a fase promete pt-BR. A
        *ausência* do checkpoint era classificada; a **ilegibilidade** não.

        Ler o checkpoint virou passo próprio para que a classificação seja por **onde** falhou:
        aqui se sabe que o que está sendo lido é um checkpoint, e as pistas de texto de
        `cli._CHECKPOINT_PISTAS` teriam de adivinhar isso de uma mensagem do `torch` que não
        contém nem `.pt` nem `state_dict`.
        """
        import tempfile

        app_tkinter = self._app_tkinter()
        with tempfile.TemporaryDirectory() as pasta:
            ruim = Path(pasta) / "piece_classifier.pt"
            ruim.write_text("isto não é um checkpoint", encoding="utf-8")
            with patch.object(app_tkinter, "DEFAULT_MODEL_PATH", ruim):
                with self.assertLogs(app_tkinter.logger, level="ERROR") as registro:
                    # O PDF nem precisa existir: a instalacao e conferida antes da entrada.
                    codigo = app_tkinter.selftest(pdf=Path("qualquer.pdf"))

        self.assertEqual(codigo, 3, "o código é o de checkpoint, e não o de falha inesperada")
        texto = chr(10).join(registro.output)
        self.assertIn("não pôde ser lido", texto, "e a frase é pt-BR")
        self.assertIn("arch_version", texto, "com o nome do campo que o usuário vai conferir")

    def test_pdf_corrompido_e_2_e_nao_1(self) -> None:
        """**A primeira das três falhas da Fase 18**, e ela era classificada ao contrário.

        No `.exe` um PDF corrompido saía com **1** -- que quer dizer "o programa falhou" --
        mais um traceback do `pymupdf` em inglês. Quem falhou foi o arquivo que o usuário
        escolheu, e 2 é o código de entrada inválida em todos os `cvoff-*` (S-126). Não havia
        razão para o auto-teste ser a exceção.

        **Ele não pede checkpoint de verdade, e isso é o item dentro do item.** A primeira
        versão pedia -- a carga do modelo vem antes da abertura do PDF --, e o resultado
        apareceu no log da CI: `SKIPPED`. Um guarda que só roda na máquina que já tem o
        checkpoint não guarda a CI, que é justamente onde o `.exe` de outra pessoa é montado.
        O modelo é dispensado com um `model_session` neutro; o que se testa aqui é o PDF.
        """
        import tempfile
        from contextlib import contextmanager

        app_tkinter = self._app_tkinter()

        @contextmanager
        def _sem_modelo(*_args: object, **_kwargs: object):  # noqa: ANN202
            yield (None, "cpu")

        with tempfile.TemporaryDirectory() as pasta:
            ruim = Path(pasta) / "corrompido.pdf"
            ruim.write_bytes(b"%PDF-1.4" + bytes([10]) + b"isto nao e um pdf" + bytes([10]))
            # So precisa **existir**: a guarda de ausencia e outra, e tem teste proprio.
            fingido = Path(pasta) / "piece_classifier.pt"
            fingido.write_text("o carregamento esta remendado abaixo", encoding="utf-8")
            servico = patch.object(
                app_tkinter.OcrService, "model_session", _sem_modelo, create=False
            )
            with patch.object(app_tkinter, "DEFAULT_MODEL_PATH", fingido), servico:
                with self.assertLogs(app_tkinter.logger, level="ERROR") as registro:
                    codigo = app_tkinter.selftest(pdf=ruim)

        self.assertEqual(codigo, 2, "entrada inválida, e não falha do programa")
        self.assertIn("não foi possível abrir", chr(10).join(registro.output))

    def test_o_checkpoint_bom_nao_cai_na_guarda_nova(self) -> None:
        """A guarda não pode transformar instalação boa em erro: o passo novo é só a carga."""
        app_tkinter = self._app_tkinter()
        modelo = PROJETO / "models" / "piece_classifier.pt"
        if not modelo.exists():
            self.skipTest("sem checkpoint neste checkout")
        with patch.object(app_tkinter, "DEFAULT_MODEL_PATH", modelo):
            # Um PDF que nao existe: o que se testa e que a carga do modelo **passou** -- o
            # codigo que sai e o do PDF (2), e nao o do checkpoint (3).
            self.assertEqual(app_tkinter.selftest(pdf=Path("nao_existe.pdf")), 2)


class _RootFalsa:
    """`after(0, fn)` executa na hora. Num teste não há laço de eventos para agendar nada."""

    def __init__(self) -> None:
        self.agendados: list[str] = []

    def after(self, _atraso: int, funcao):  # noqa: ANN001, ANN202 - assinatura do Tk
        self.agendados.append(getattr(getattr(funcao, "func", funcao), "__name__", "?"))
        funcao()


def _janela_minima(app_tkinter, *, result_panel=None):  # noqa: ANN001, ANN202
    """A janela reduzida ao que `_ocr_worker` toca, com os métodos **reais** amarrados nela.

    Montar o `ChessOcrTkApp` inteiro exigiria Tk, checkpoint e PDF; o que se testa aqui é o
    `except`, e ele não depende de nenhum dos três. É o mesmo recurso da S-142.
    """
    janela_class = type(
        "JanelaMinima",
        (),
        {
            "_ocr_worker": app_tkinter.ChessOcrTkApp._ocr_worker,
            "_on_ocr_empty": app_tkinter.ChessOcrTkApp._on_ocr_empty,
            "_on_ocr_error": app_tkinter.ChessOcrTkApp._on_ocr_error,
            "_set_status": lambda self, texto: self.status.append(texto),
            "_show_results": lambda self, *_args: self.lidos.append(_args),
            "_finish_ocr_ui": lambda self: self.status.append("<fim>"),
        },
    )
    janela = janela_class()
    janela.root = _RootFalsa()
    janela.result_panel = result_panel
    janela.status = []
    janela.lidos = []
    return janela


class OcrWorkerLogTests(unittest.TestCase):
    """O worker de OCR registra a exceção como os outros cinco (S-125).

    Era o único dos seis que a engolia: o usuário do `.exe` recebia uma linha de texto e o
    arquivo de log não recebia nada. Junto com a S-127 -- que faz o arquivo existir num
    bundle -- é o par que fecha "reconhecer a página quebrou e ninguém sabe por quê".
    """

    def setUp(self) -> None:
        self.app_tkinter = SelftestTests._app_tkinter()
        self.origem = self.app_tkinter.RecognitionOrigin.for_page("livro.pdf", 16)
        self.caixas: list[tuple[str, str, str]] = []
        for nome in ("showerror", "showinfo"):
            original = getattr(self.app_tkinter.messagebox, nome)
            self.addCleanup(setattr, self.app_tkinter.messagebox, nome, original)
            setattr(
                self.app_tkinter.messagebox,
                nome,
                lambda titulo, texto, _n=nome: self.caixas.append((_n, titulo, texto)),
            )

    def _roda(self, erro: Exception, *, nivel: str):
        janela = _janela_minima(self.app_tkinter)

        def _levanta():
            raise erro

        with self.assertLogs(self.app_tkinter.logger, level=nivel) as registro:
            janela._ocr_worker(run=_levanta, origin=self.origem)
        return janela, registro

    def test_a_falha_de_verdade_vai_para_o_log_com_traceback(self) -> None:
        _janela, registro = self._roda(RuntimeError("o checkpoint é de outra arch_version"), nivel="ERROR")

        self.assertEqual(len(registro.records), 1)
        self.assertEqual(registro.records[0].levelname, "ERROR")
        self.assertIn("Traceback", registro.output[0])
        self.assertIn("pdf:livro.pdf:page:16", registro.output[0])

    def test_a_falha_de_verdade_continua_sendo_caixa_de_erro(self) -> None:
        self._roda(RuntimeError("o checkpoint é de outra arch_version"), nivel="ERROR")

        self.assertEqual([nome for nome, _t, _x in self.caixas], ["showerror"])
        self.assertIn("arch_version", self.caixas[0][2])

    def test_pagina_sem_diagrama_nao_e_erro(self) -> None:
        """Prosa, índice e página de soluções são a maioria de um livro. Não são falha."""
        janela, registro = self._roda(
            self.app_tkinter.NoBoardDetectedError("Nenhum tabuleiro foi detectado."), nivel="INFO"
        )

        self.assertEqual(registro.records[0].levelname, "INFO")
        self.assertNotIn("Traceback", registro.output[0])
        # **Nem caixa informativa, desde a S-164.** A S-125 tirou a caixa vermelha daqui; o que
        # sobrou era um clique obrigatório no caso mais comum do programa -- virar página em livro
        # de exercícios cai em prosa a cada duas ou três. A frase foi para o rodapé, que tem
        # severidade própria desde a S-163 e não precisa interromper para ser lida.
        self.assertEqual([nome for nome, _t, _x in self.caixas], [])
        self.assertTrue(
            any("Selecionar área" in texto for texto in janela.status),
            "a saída ficou sem a única dica que a caixa dava: use Selecionar área (OCR)",
        )

    def test_o_caminho_e_o_tipo_da_excecao_e_nao_o_texto_dela(self) -> None:
        """A separação era `"Nenhum tabuleiro foi detectado" in str(exc)`: traduzir a
        mensagem, ou mudar uma palavra dela, silenciosamente devolvia a caixa vermelha."""
        janela = self._roda(self.app_tkinter.NoBoardDetectedError("outra frase qualquer"), nivel="INFO")[0]

        self.assertEqual([nome for nome, _t, _x in self.caixas], [])
        self.assertTrue(any("outra frase qualquer" in texto for texto in janela.status))

    def test_a_ui_e_liberada_nos_dois_caminhos(self) -> None:
        """O `finally` é o que devolve os botões. Perdê-lo travaria o OCR para sempre."""
        for erro in (RuntimeError("qualquer"), self.app_tkinter.NoBoardDetectedError("nada aqui")):
            with self.subTest(erro=type(erro).__name__):
                janela, _registro = self._roda(erro, nivel="INFO")
                self.assertEqual(janela.status[-1], "<fim>")


class FilhoLeveTests(unittest.TestCase):
    """O processo-filho da varredura não reexecuta o programa que o criou (S-141).

    **O que estava em jogo, medido nesta máquina:** reimportar `app_tkinter.py` como
    `__mp_main__` custa **3,14 s e 2.212 módulos** -- `torch`, `cv2`, `PIL` e os seis painéis
    da interface --, e o filho não usa nenhum deles: ele lê PGN e reproduz lances. Com dez
    processos são ~31 s de CPU e ~2,3 GB jogados fora no arranque de cada varredura.

    O teste roda um script de verdade em subprocesso porque **é o único jeito de ver o que o
    filho faz**: dentro do pytest o `__main__` é o do pytest, e a pergunta desapareceria.
    """

    ROTEIRO = '''
import multiprocessing as mp, os, sys, pathlib
sys.path.insert(0, {src!r})

# O rastro: cada execucao deste arquivo acrescenta uma linha. O pai poe uma; um filho que
# reimporte o `__main__` poe outra. E o **peso**: o que a janela de verdade importa.
pathlib.Path({rastro!r}).open("a", encoding="utf-8").write("uma\\n")
import numpy, chess  # noqa: F401  -- os dois mais caros que este ambiente tem sempre

def main():
    mp.freeze_support()
    from chess_diagram_ocr.games_db import scan_by_positions
    tabuleiro = chess.Board()
    for lance in ("e4", "e5", "f4"):
        tabuleiro.push_san(lance)
    achado = scan_by_positions([pathlib.Path({base!r})], {{tabuleiro.board_fen()}}, workers=2)
    print("casamentos:", achado.counts.get(tabuleiro.board_fen(), 0))

if __name__ == "__main__":
    main()
'''

    def _roda(self, pasta: Path) -> tuple[int, str]:
        import subprocess

        base = pasta / "base.pgn"
        base.write_text(
            '[Event "x"]\n[White "Anderssen"]\n[Black "Kieseritzky"]\n\n1. e4 e5 2. f4 *\n' * 400,
            encoding="utf-8",
        )
        rastro = pasta / "rastro.txt"
        roteiro = pasta / "varre.py"
        roteiro.write_text(
            self.ROTEIRO.format(
                src=str(PROJETO / "src"), rastro=str(rastro), base=str(base)
            ),
            encoding="utf-8",
        )
        concluido = subprocess.run(
            [sys.executable, str(roteiro)], capture_output=True, text=True, timeout=300
        )
        self.assertEqual(concluido.returncode, 0, concluido.stderr)
        return len(rastro.read_text(encoding="utf-8").splitlines()), concluido.stdout

    def test_o_filho_nao_reexecuta_o_script_do_pai(self) -> None:
        """**O item.** Uma linha no rastro é o pai; três seriam o pai mais os dois filhos."""
        import tempfile

        with tempfile.TemporaryDirectory() as pasta:
            execucoes, saida = self._roda(Path(pasta))
        self.assertEqual(execucoes, 1, "só o pai executou o script; os filhos arrancaram nus")
        # As 400 copias da mesma partida, achadas pelos dois processos e fundidas: a economia
        # nao pode ter custado resposta, que e a outra metade do criterio de aceite.
        self.assertIn("casamentos: 400", saida, "e a varredura respondeu a mesma coisa")

    def test_a_supressao_diz_se_aconteceu_e_devolve_o_main_no_fim(self) -> None:
        """Um `pass` silencioso passaria por uma economia que não existiu."""
        from chess_diagram_ocr.games_db import _filho_sem_o_main_do_pai

        principal = sys.modules["__main__"]
        antes = getattr(principal, "__file__", None)
        with _filho_sem_o_main_do_pai() as suprimiu:
            self.assertEqual(suprimiu, antes is not None)
            self.assertFalse(hasattr(principal, "__file__"))
        self.assertEqual(getattr(principal, "__file__", None), antes, "o pai fica como estava")

    def test_num_bundle_congelado_a_supressao_nao_roda(self) -> None:
        """Ali quem intercepta o filho é o `freeze_support` (S-55), e o caminho é outro."""
        from chess_diagram_ocr.games_db import _filho_sem_o_main_do_pai

        with patch.object(sys, "frozen", True, create=True):
            with _filho_sem_o_main_do_pai() as suprimiu:
                self.assertFalse(suprimiu)
                self.assertTrue(hasattr(sys.modules["__main__"], "__file__"))


if __name__ == "__main__":
    unittest.main()
