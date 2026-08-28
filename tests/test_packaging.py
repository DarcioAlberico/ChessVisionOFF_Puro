"""O que muda quando o programa é um `.exe` em vez de um checkout (S-55).

Um único defeito de empacotamento é caro de um jeito diferente dos outros: ele só aparece
na máquina de outra pessoa, e o sintoma é uma janela que some. Estes testes cobrem a parte
que **pode** ser verificada aqui — para onde o programa aponta quando `sys.frozen` está
posto — e o resto o `--selftest` responde na máquina de destino.
"""

from __future__ import annotations

import importlib
import logging
import sys
import tempfile
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


class LogQueNaoCresceParaSempreTests(unittest.TestCase):
    """O arquivo de log rotaciona, e sem console não há handler de console (S-389).

    O arquivo grava em DEBUG por decisão da S-126, e DEBUG num programa que lê 402 páginas são
    dezenas de MB por sessão. E no bundle da S-55 o `.exe` é montado com `console=False`: aí
    `sys.stderr` é `None`, o `StreamHandler` nasce sem fluxo e **falha a cada registro**.
    """

    def setUp(self) -> None:
        import shutil

        import chess_diagram_ocr.logging_setup as setup

        # A pasta some **depois** de os handlers fecharem: no Windows um arquivo aberto não é
        # apagável, e o `addCleanup` roda na ordem inversa do registro.
        self.pasta = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.pasta, True)
        self.setup = setup
        self.raiz = logging.getLogger()
        self.handlers_antes = list(self.raiz.handlers)
        self.configurado_antes = setup._configured

        def restaurar() -> None:
            for handler in list(self.raiz.handlers):
                if handler not in self.handlers_antes:
                    self.raiz.removeHandler(handler)
                    handler.close()
            for handler in self.handlers_antes:
                if handler not in self.raiz.handlers:
                    self.raiz.addHandler(handler)
            setup._configured = self.configurado_antes

        self.addCleanup(restaurar)
        setup._configured = False
        # `basicConfig` não faz nada com a raiz já povoada, e o pytest põe os dele lá:
        # sem esvaziar, o teste afirmaria sobre os handlers do runner.
        for handler in list(self.raiz.handlers):
            self.raiz.removeHandler(handler)

    def test_o_arquivo_de_log_rotaciona(self) -> None:
        from logging.handlers import RotatingFileHandler

        self.setup.configure_logging(log_file=self.pasta / "cvoff.log")

        rotativos = [h for h in self.raiz.handlers if isinstance(h, RotatingFileHandler)]

        self.assertEqual(len(rotativos), 1)
        self.assertGreater(rotativos[0].maxBytes, 0)
        self.assertGreater(rotativos[0].backupCount, 0)

    def test_sem_stderr_nao_ha_handler_de_console(self) -> None:
        with patch.object(sys, "stderr", None):
            self.setup.configure_logging(log_file=self.pasta / "cvoff.log")

        de_fluxo = [
            h
            for h in self.raiz.handlers
            if type(h) is logging.StreamHandler  # noqa: E721 - o de arquivo herda dele
        ]

        self.assertEqual(de_fluxo, [])
        logging.getLogger(__name__).info("um registro que não pode levantar")

    def test_com_stderr_o_console_continua_la(self) -> None:
        self.setup.configure_logging(log_file=self.pasta / "cvoff.log")

        de_fluxo = [h for h in self.raiz.handlers if type(h) is logging.StreamHandler]  # noqa: E721

        self.assertEqual(len(de_fluxo), 1)

    def test_sem_destino_o_padrao_e_o_de_default_log_file(self) -> None:
        """Vinte e três dos 41 comandos não passavam `log_file`, e o `.exe` ficava sem rastro."""
        with patch.dict("os.environ", {"CVOFF_LOG_DIR": str(self.pasta)}):
            self.setup.configure_logging()

        arquivos = [h for h in self.raiz.handlers if hasattr(h, "baseFilename")]

        self.assertEqual(len(arquivos), 1)
        self.assertTrue(str(arquivos[0].baseFilename).startswith(str(self.pasta)))


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

    LIMITE = 2291
    """Linhas de `app_tkinter.py`. Ver o docstring da classe antes de mudar.

    **2.090 → 2.092 na Fase 39**, e as onze são as quatro linhas de exportação (`.md`, `.html`,
    `.rtf` e o PDF pesquisável) mais as sete da Fase 38 -- todas entradas em `_comandos`, uma por
    comando do catálogo. A janela continua sem decidir nada sobre texto: ela liga nome a função.

    **2.000 → 2.090 na Fase 37**, e as 109 são o editor de texto chegando à janela. Nenhuma delas
    decide coisa nenhuma sobre texto:

    - **dezessete** são entradas em `_comandos`, uma por comando novo do catálogo (S-240). Elas são
      a amarração nome → função, que é a única coisa deste assunto que precisa dos widgets;
    - **quinze** são `_on_texto` e `_desfazivel`/`_desfaziveis`/`_foco`: o molde de `_on_result`, e
      a escolha de quem desfaz -- que **não** é decidida aqui: a regra mora em `ui/desfazivel.py`, e
      esta janela só pergunta quem tem o foco (S-243);
    - **catorze** são `_interruptores`, que junta a marca de vista do PDF com a de modo bloco da aba
      de texto -- um item de menu sem a marca desenharia estado como se fosse ação;
    - as demais são docstring e comentário, inclusive o da conferência de `conferir_dono` no
      `_bind_shortcuts` (S-244), que é o que faz "declarei e não atendo" levantar na montagem.

    **1.972 → 2.000 na S-234**, e as vinte e oito são o auto-teste passando pelo cromo. Quinze são
    `_provar_as_peles` -- criar a raiz retirada, desistir em silêncio numa máquina sem display, e
    destruí-la no `finally` --, seis são o passo novo no fim do `selftest` com o código de saída
    **5**, e as outras sete são o `import` e o comentário que diz por que o auto-teste é o lugar
    disto: ele já é o roteiro headless que o `CONTRIBUTING` manda usar para dirigir a interface sem
    clicar, e o cromo é justamente onde a Fase 35 acrescentou modos de falha.

    **O laço não está aqui**, e é o que torna a afirmação testável: `degradacao.provar_as_peles`
    recebe uma raiz, então a suíte faz a mesma pergunta com a raiz compartilhada do processo em vez
    de criar uma segunda -- que é o que `tests/tk_root.py` documenta como não confiável no Windows.

    **1.930 → 1.972 na S-232**, e as quarenta e duas são o eixo de densidade chegando à janela.
    Nenhuma delas decide o que "compacta" significa:

    - **catorze** são `_escolher_densidade`, que é a amarração que só este objeto pode fazer -- ele
      tem o `AppState` e o `StringVar`, e é onde mora a diferença entre *não decidi* e *decidi o
      que a pele sugeria*, que é o item inteiro;
    - **nove** estão no `remontar_cromo`: resolver a densidade, sincronizar a variável, passá-la ao
      tema e à fita, e trocar o `padx=10, pady=6` cravados pelo que `tipografia.folgas` devolve;
    - **doze** são a variável e o docstring que explica por que ela guarda a densidade **resolvida**
      enquanto o estado guarda a **escolhida** -- `radiobutton` não sabe marcar "vazio";
    - as **sete** restantes são o `import`, a entrada em `_comandos`, o `escolhas=` do menu, o
      `set` da restauração e o `apply_theme` da abertura, que passou a caber em cinco linhas para
      levar a densidade da pele antes de o disco ser lido.

    **A escala não está aqui**, e é o que faz a subida ser de quarenta e duas e não de duzentas:
    quanto vale cada folga, como ela deriva da fonte do sistema, o fator de cada densidade e o piso
    da altura de linha são de `ui/tipografia.py`, que não importa `tkinter` -- e a resolução
    "ambiente, senão escolha, senão sugestão da pele" é de `ui/pele.py`.

    **1.919 → 1.930 na S-231**, e as onze são a paleta de comandos ligada à janela: o `import`, a
    entrada em `_comandos` e o método de sete linhas que abre a paleta passando o **mesmo** mapa
    que o menu e os atalhos recebem -- que é o que faz "a paleta cobre o catálogo inteiro" ser
    consequência da amarração, e não uma segunda lista.

    **A paleta em si não está aqui**, e é o que faz a subida ser de onze e não de duzentas: o
    filtro, a ordem, o motivo da linha cinza e a janela são `ui/paleta_de_comandos.py`, que não
    conhece esta classe. O filtro é puro e tem os testes dele sem abrir janela nenhuma.

    **1.868 → 1.919 na Fase 34**, e as cinquenta e uma se dividem em três e quarenta e oito.

    As **três** são a S-229: `desfazer`, `refazer` e `limpar_tabuleiro` entrando em `_comandos`,
    uma linha cada, ligando o nome ao `ResultPanel`. A pilha, o teto de cem estados, as sete
    origens de mudança, os dois botões e o motivo de cada um estar cinza são `ui/historico.py` e
    `ui/result_panel.py` -- a janela só amarra os nomes, que é o que o catálogo da S-324 comprou.

    As **quarenta e oito** são a S-230, e elas se pagam por não existirem em outro lugar: a linha
    de escolha do conjunto na Configuração (`_build_piece_set_row`, com os três `Radiobutton` e o
    campo de pasta que `ui/campos.py` valida), a troca em execução (`_escolher_conjunto`, que
    redesenha e grava) e as três linhas que restauram do disco o que estava guardado. **O registro
    de conjuntos e o desenho não estão aqui**: `ui/conjuntos.py` declara os três e `PieceImages`
    os desenha, e nenhum dos dois conhece a janela.

    É a linha do meio do argumento da S-31, e ela continua valendo: o que fica aqui é a **ligação**
    -- qual widget, em que aba, chamando qual nome --, e o que decide alguma coisa desce para
    `ui/`. Quarenta e oito linhas de widget de Configuração são caras, e são a parte deste arquivo
    que a decomposição do `ROADMAP_UI` ainda vai alcançar.

    **1.865 → 1.868 na S-227**, e as três são a terceira pele entrando: o `import`, e o `elif` que
    manda montar a fita na mesma faixa em que a "Foco" monta a fila. A fita inteira -- os quatro
    grupos, o cabeçalho, o botão de ícone com rótulo e a quebra por grupo -- é `ui/fita.py`, que
    não conhece a janela.

    **É a medida do que as S-324 a S-222 compraram**: a primeira pele custou dezesseis linhas
    aqui; a terceira custou três.

    **1.862 → 1.865 na S-226**, e as três são a faixa de abas trocando de peso na pele "Foco":
    o `if` do painel, a linha que aplica o estilo e o comentário que diz por que as sete abas
    continuam lá. Os sete rótulos **não** custaram linha nenhuma: eles já estavam escritos, e o
    que a S-226 fez foi movê-los para `ui/abas.py` e referenciá-los no lugar do literal.

    **1.859 → 1.862 na S-224**, e as três são o cromo escuro chegando à janela: a linha que
    pergunta à pele qual tema aplicar na abertura, e as duas que fazem a mesma pergunta na troca.
    `registrar_estilos` saiu daqui e virou `apply_theme`, que escolhe o tema, reaplica os estilos
    nomeados **e** repinta o que foi pintado fora do `Style`. A paleta inteira -- nove papéis de
    cromo escuro, a fronteira do documento e a separação de `PROBLEMA_TEXTO` -- é `ui/tokens.py`.

    **1.843 → 1.859 na S-223**, e as dezesseis são a pele "Foco" entrando na janela. Três são a faixa
    onde a fila mora -- um `Frame` vazio acima do divisor, que na pele clássica não custa altura
    nenhuma. Seis estão no `remontar_cromo`: descobrir a montagem da pele, esvaziar a faixa,
    desenhar a fila quando for o caso, e passar a montagem adiante. As quatro últimas remontam o
    cromo depois de o disco ser lido -- a janela sobe na clássica porque o menu é montado antes
    de haver estado, e sem isso quem fechou na "Foco" reabriria na clássica.

    As três últimas amarram os comandos que até aqui só existiam como botão -- cancelar
    exportação e os dois de zoom --, e é a trava de `menu.montar` que as cobrou: declarar o item
    sem amarrar a função levanta, e foi o que aconteceu na primeira tentativa.

    **A fila em si é `ui/fila.py`**, que não conhece a janela: ela recebe um pai e o mapa de
    comandos, e sai do catálogo.

    **1.821 → 1.843 na S-222**, e as vinte e duas são o `remontar_cromo` com o docstring que
    explica **o que ele não faz** -- que é a metade cara do item. As quatro linhas de código são
    quatro chamadas: reaplicar os estilos nomeados, esvaziar o cache de ícones, mandar o painel
    de PDF refazer as barras, e refazer a barra de menus. As outras duas são a comparação em
    `_escolher_pele` que evita remontar quando a pele escolhida já é a que está valendo.

    **O trabalho de verdade não está aqui**, e por isso a subida foi de vinte e duas e não de
    duzentas: destruir e refazer as duas barras, devolver o `state` dos seis botões e
    ressincronizar o nome do livro, o zoom e o rótulo de quem estava ligado são tudo de
    `ui/pdf_panel.remontar_cromo`, junto dos widgets que ele mesmo criou.

    **1.808 → 1.821 na S-221**, e as treze são a pele virando estado da janela. Seis são o
    `_escolher_pele`, que é a amarração que só este objeto pode fazer -- ele tem o `AppState` e o
    `StringVar`; três são a variável e o docstring que explica por que ela nasce do ambiente (o
    menu é montado **antes** de o estado ser lido, e é a linha do `_restore_state` que a corrige);
    as quatro restantes são o `import`, a entrada em `_comandos`, o `escolhas=` do menu e o
    `set` da restauração.

    **O registro em si não está aqui**, e é o que faz esta subida ser de treze e não de cinquenta:
    quais peles existem, qual é a padrão, o que fazer com um nome inválido e de onde vem a
    variável de ambiente são todos de `ui/pele.py`, que não importa `tkinter` e tem os seus
    dezesseis testes sem abrir janela.

    **1.800 → 1.808 na S-324**, e as oito são o preço de a linha do conjunto de campo passar a
    tirar o rótulo do catálogo. Nenhuma é lógica: `comandos.rotulo_de_botao("tirar_do_campo")` é
    mais largo que `"Tirar o selecionado"`, e dois botões que cabiam numa linha e em três passaram
    a caber em seis cada. **O import não cresceu** -- `estilos` saiu e `comandos` entrou no lugar,
    porque a ênfase do "Anotar página" também vem do registro agora.

    É uma troca, e ela está registrada dos dois lados: a janela ficou 8 linhas maior e o programa
    ficou com **um** lugar onde se lê o que cada comando é. Enquanto eram três lugares, o mesmo
    `ler_pagina` se chamava "Ler esta página" no menu e "OCR todos diagramas" no botão -- e nada
    comparava os dois. O que deve encolher aqui é `_build_field_row` inteira, que é layout de um
    painel dentro da janela; a S-31 continua sendo esse alvo, e a S-324 não era a hora.

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

    **2.098 → 2.173 nas Fases 46 a 48**, e as 66 são a sala de estudo chegando ao resto do
    programa (S-280 a S-287). O que **saiu**: os vinte e quatro comandos moram em
    `study_panel.COMANDOS_DA_ABA` e a janela os liga por tabela, como já fazia com os do editor --
    não há um `lambda p: p.promover_variante()` sequer aqui. O que **ficou** são as quatro portas
    por onde o livro entra na sala, e cada uma é a janela sendo a janela: qual recorte a aba
    Resultado tem na memória, o que a aba Texto leu ao lado daquele diagrama, para que página o
    visualizador deve ir, e onde estão os `.pgn` do usuário. Ligar painel a painel é o que só quem
    montou os dois pode fazer, pela mesma razão que `_reload_dataset_panel` ficou na S-116.

    **2.173 → 2.195 nas Fases 49 e 50**, e as 22 são as duas pontas que faltavam à sala: a linha do
    estudo indo para a aba de texto (S-289) e a aba que ela alcança vindo para a frente. O que
    **saiu**: a conversão do estudo em documento é `estudo_saida.py`, o que cada formato faz continua
    sendo de `text/exportacao.py`, e os sete comandos novos chegam pela tabela de sempre. O que
    **ficou** é ligar dois painéis -- que é o que só quem montou os dois pode fazer.

    **2.195 → 2.261 nas Fases 53 a 55**, e as 66 são seis defeitos de perda de trabalho humano sendo
    consertados na única camada que podia consertá-los. O que **saiu**: a leitura do conjunto de
    campo virou `field_draft.diagramas_ja_anotados`, e é lá que mora o docstring que explica por
    que a guarda pergunta ao arquivo e não ao rascunho da tela (S-301); a resposta a "qual
    retângulo está selecionado" virou `pdf_panel.selected_box`, com a explicação junto (S-306).
    O que **ficou** aqui são as duas perguntas que só a janela pode fazer -- ela é quem tem o
    `messagebox` e quem sabe que folha está aberta --, e ligar o visualizador ao conjunto de
    campo, que é o mesmo tipo de costura entre painéis que a S-116 já tinha deixado. As oito
    últimas são a guarda de mapeamento da S-311, o consentimento por endereço da S-319 e o
    sinalizador de ordem da S-322 -- e as três **têm** de morar aqui: quem grava o estado da
    janela é a janela, quem marca o consentimento é quem mostrou a caixa que o pediu, e quem
    sabe se o estado lido já chegou aos widgets é quem os montou. A S-322 é a que mais custa em
    linhas e a que mais paga: sem ela, **nada** do que a S-156, a S-221 e a S-291 prometem
    lembrar sobrevivia a fechar a janela -- o arquivo em disco era reescrito com os padrões de
    fábrica antes de a primeira linha de restauração rodar.

    **2.261 → 2.274 na Fase 57**, e as treze são de dois itens que só a janela podia costurar. A
    S-329 liga o campo de DPI ao visualizador -- **três linhas**, porque a espera pelo fim da
    digitação e a re-rasterização foram para `pdf_panel.observar_dpi`, que é quem sabe que a
    imagem em memória envelheceu. A S-347 guarda a chave do estudo que a sessão anterior deixou
    aberto e a entrega ao painel quando o livro dela abre: quem lê o `AppState` é a janela, e o
    campo `estudo_aberto` existia desde a S-271 sendo gravado e nunca lido.

    **2.274 → 2.291 na Fase 63**, e as dezessete são de cinco itens da janela: o `Esc` do
    diálogo de correção remota (S-395); o docstring de `_focus_result_tab`, que passou a
    explicar por que a seleção é pelo **rótulo** da aba e não pelo painel -- o painel nunca foi
    aba, e o `TclError` disso morria num `logger.debug` (S-397); a contagem das abas refeita
    depois de varrer o livro, que é o gesto que a muda (S-398); e o `StringVar` do conjunto de
    campo, que subiu para o `__init__` porque a linha que o hospedava é refeita a cada troca
    de pele e a escolha do usuário voltava ao primeiro regime da lista (S-399); e a Galeria
    entrando na conferência de `atalhos.conferir_dono`, que é uma linha e é onde ela tinha de
    entrar -- quem confere os donos de ação é quem liga os atalhos (S-400).

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

    def test_o_que_nao_e_dependencia_nao_entra_no_bundle(self) -> None:
        """`scipy` e `scikit-image` vêm no ambiente pelo clone da segunda opinião local, e o
        PyInstaller coleta o que **está instalado** -- 95 MB que ninguém declarou (S-387)."""
        excludes = self.texto.split("excludes = [", 1)[1].split("\n]", 1)[0]
        for pacote in ("scipy", "skimage", "pyarrow"):
            with self.subTest(pacote=pacote):
                self.assertIn(f'"{pacote}"', excludes)

    def test_o_spec_e_lintado(self) -> None:
        """O arquivo tem `# noqa` espalhado, que só faz sentido se alguém estiver lintando --
        e até a S-391 nem `ruff` nem `mypy` o viam, porque os dois olham `.py`."""
        pyproject = (PROJETO / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('extend-include = ["*.spec"]', pyproject)


class DependenciasDoBundleTests(unittest.TestCase):
    """O que é obrigatório viaja dentro do `.exe`; o que só o teste usa, não (S-386)."""

    def setUp(self) -> None:
        self.pyproject = (PROJETO / "pyproject.toml").read_text(encoding="utf-8")
        self.obrigatorias = self.pyproject.split("dependencies = [", 1)[1].split("\n]", 1)[0]

    def test_o_pandas_nao_e_dependencia_obrigatoria(self) -> None:
        self.assertNotIn('"pandas', self.obrigatorias)

    def test_o_pandas_continua_disponivel_para_o_teste(self) -> None:
        """Quatro arquivos de teste o usam como segunda régua do CSV de rótulos."""
        dev = self.pyproject.split("dev = [", 1)[1].split("\n]", 1)[0]
        self.assertIn('"pandas', dev)

    def test_nenhum_modulo_de_producao_importa_pandas(self) -> None:
        """A guarda que impede a dependência de voltar por uma linha de import."""
        raiz = PROJETO / "src" / "chess_diagram_ocr"
        culpados = [
            caminho.relative_to(PROJETO).as_posix()
            for caminho in raiz.rglob("*.py")
            if "import pandas" in caminho.read_text(encoding="utf-8")
        ]
        self.assertEqual(culpados, [])


class ModelosAoLadoDoExecutavelTests(unittest.TestCase):
    """O build leva os três modelos para `models/`, e diz o que falta sem cada um (S-388).

    O motor `glifo` precisa dos pesos **e** do `char_meta.json` -- `carregar_classificador` acha
    o `.pt` ao lado do metadado --, e o build copiava só o de peças: no `.exe`, a aba Texto
    oferecia um motor que nunca subia.
    """

    def test_os_tres_modelos_estao_declarados(self) -> None:
        import importlib.util

        caminho = PROJETO / "packaging" / "build_windows.py"
        spec = importlib.util.spec_from_file_location("build_windows_teste", caminho)
        assert spec is not None and spec.loader is not None
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)

        nomes = [nome for nome, _motivo in modulo.MODELOS_QUE_ACOMPANHAM]

        self.assertEqual(nomes, ["piece_classifier.pt", "char_classifier.pt", "char_meta.json"])
        for _nome, motivo in modulo.MODELOS_QUE_ACOMPANHAM:
            self.assertGreater(len(motivo), 20, "cada ausência diz a consequência dela")



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
