"""O que se perde ao fechar a janela, decidido fora dela (S-60).

`app_tkinter._on_close` gravava o estado e chamava `root.destroy()` sem perguntar nada. As
oito threads do app são `daemon=True` e nenhuma é aguardada, então um treino de ~9 min por
época morria ali em silêncio -- e o treino não tinha cancelamento, então fechar a janela era
o único jeito de pará-lo.

Sem Tk aqui de propósito: a decisão de **o que dizer** é o conteúdo do item, e ela é
testável sem abrir janela.
"""

from __future__ import annotations

import ast
import tempfile
import textwrap
import threading
import unittest
from collections.abc import Sequence
from pathlib import Path

from qt_app import MOTIVO, TEM_PYQT

from chess_diagram_ocr.ui.busy import FORA_DO_REGISTRO, BusyRegistry

RAIZ = Path(__file__).resolve().parents[1]

ARQUIVOS_COM_THREAD = sorted((RAIZ / "src" / "chess_diagram_ocr" / "qt").glob("*.py"))
"""Onde a interface abre threads.

**Era `ui/` mais o `app_tkinter.py` até o corte (S-506).** Depois dele `ui/` não abre thread
nenhuma -- é a camada pura --, e quem as abre é `qt/`. Apontar a varredura para a pasta antiga
deixaria a guarda passando em verde sobre zero threads, que é o modo de falha que ela existe
para evitar: a S-60 cobriu as duas operações longas que existiam então e as dez seguintes
entraram em silêncio."""

SEM_REGISTRO = FORA_DO_REGISTRO
"""A tabela mudou de arquivo no F9-C3: ela mora em `ui/busy.py` e este nome é o apelido local.

**Por que ela saiu daqui.** Enquanto morava no teste, só o teste a via -- e o portão
`caissa.ui.audit.progresso`, que existe para achar operação longa sem progresso, não tinha como
enxergar as duas leituras que o ciclo 2 declarou aqui em vez de registrar. A decisão é decisão e
mora em `ui/`; as asserções abaixo continuam sendo as mesmas, mais uma nova (ver
`test_a_lista_de_excecoes_nao_guarda_quem_ja_registra`).

**Ela encolheu de cinco entradas para três**, porque `marcas.pedir` e
`painel_do_dataset._reler_agora` passaram a chamar `busy.register`. Isso é a catraca apertando:
duas exceções a menos, e um teste a mais que impede uma exceção de sobreviver ao registro que a
tornou desnecessária."""


CLASSES_DE_THREAD = (
    "Thread",
    "Timer",
    "ThreadPoolExecutor",
    "ProcessPoolExecutor",
    "Process",
    "Pool",
    "QThread",
    "QRunnable",
    # **Processo externo é operação de fundo pela mesma pergunta** (F9-C7 §4.3, formas f e g;
    # F9-C8 forma b). O portão não pergunta "abriu uma thread?", pergunta "há trabalho correndo
    # que a janela não mostra?". `ThreadPool` é `multiprocessing.pool.ThreadPool`: o termo final
    # difere de `Pool`, e o irmão mais usado dele escapava inteiro.
    "Popen",
    "QProcess",
    "ThreadPool",
)
"""As classes da biblioteca cuja construção abre uma linha de execução paralela (F9-C5 §5).

**Era `("threading.Thread", "Tarefa")` -- duas grafias literais comparadas com
`ast.unparse(no.func)` --**, e o crítico do ciclo 5 plantou seis operações de fundo em `qt/`:
esta guarda e o portão `caissa.ui.audit.progresso`, que compartilham a régua, achavam **uma**,
marcavam **uma** como registrada sem registro nenhum e não viam **quatro**.
`from threading import Thread` escreve `Thread`; `threading.Timer` escreve `Timer`;
`ThreadPoolExecutor(1).submit(...)` não escreve nenhuma das duas -- e as três abrem thread do
mesmo jeito. Comparar o **último termo** do nome põe as três na mesma regra.

`Tarefa` saiu da lista de propósito: ela é `class Tarefa(QThread)`, e `_classes_de_thread` a
encontra por herança. Subclasse nova entra sozinha -- que era o furo da forma (e) da
sabotagem."""

METODOS_DE_SUBMISSAO = (
    "submit",
    "start_new_thread",
    "run_in_executor",
    "apply_async",
    # F9-C7 §4.3 (d, e) e F9-C8 (c, d). `moveToThread` é **o idioma canônico do Qt** e escapava
    # inteiro: não constrói thread no ponto de chamada e não se chama `submit`. As três do
    # `asyncio` põem uma corrotina a correr concorrente sem nomear thread nenhuma.
    "to_thread",
    "moveToThread",
    "create_task",
    "ensure_future",
    "run_coroutine_threadsafe",
)
"""Chamadas que empurram trabalho para uma linha já aberta -- o pool que nasceu no `__init__`.

`map` fica de fora **daqui**: é o nome mais comum do repositório, e um detector que gritasse em
todo `map` deixaria de ser lido, que é a outra maneira de ficar cego. Ele entra em
`METODOS_DE_POOL`, onde o receptor paga a conta da precisão."""

METODOS_DE_POOL = (
    "map",
    "imap",
    "imap_unordered",
    "starmap",
    "map_async",
    "starmap_async",
    "start",
    "tryStart",
)
"""Métodos que só são submissão **quando o receptor é um pool** -- ver `RECEPTORES_DE_POOL`.

`self._pool.map(f, itens)` roda `f` em N threads (F9-C7 §4.3, forma c) e escapava por uma
exclusão declarada: `map` estava fora de propósito. A exclusão continua certa; o que faltava era
a outra metade -- exigir que o **receptor diga que é um pool**. `tryStart` é o irmão de `start`
em `QThreadPool` (F9-C8, forma e)."""

FUNCOES_DE_PROCESSO_EXTERNO = (
    "startfile",
    "spawnl",
    "spawnle",
    "spawnv",
    "spawnve",
    "spawnlp",
    "spawnvp",
)
"""Funções que largam um programa externo correndo e devolvem na hora (F9-C8, forma g).

`os.system` e `subprocess.run` **não** entram: eles bloqueiam, e o que bloqueia é problema do
portão `caissa.ui.audit.bloqueio`, não deste."""

EMBRULHOS_DE_CHAMADA = ("partial", "partialmethod")
"""Funções que guardam uma classe para chamá-la depois (F9-C7 §4.3, forma b).

`functools.partial(threading.Thread, target=f)()` não nomeia thread nenhuma na chamada que de
fato a abre. A regra olha o **primeiro argumento**, e os dez `partial(self._ir, …)` de
`qt/painel_da_galeria.py` não acusam."""

RECEPTORES_DE_POOL = ("threadpool", "processpool", "pool", "executor")
"""Receptores em que um `.start(...)` **com argumento** é submissão, e não partida de relógio.

`start` não pode entrar em `METODOS_DE_SUBMISSAO`: `qt/` tem dezenas de
`self._relogio.start(250)`, e todo `Tarefa(...).start()` é a *partida* de uma thread que a regra
de construção já contou. Mas `QThreadPool.globalInstance().start(tarefa)` é a única forma de
enfileirar um `QRunnable` no Qt, e ela não constrói nada no ponto de chamada nem se chama
`submit`. Pede as duas coisas -- nome de pool no receptor e ao menos um argumento -- porque
`pool.start()` sem argumento liga o pool, não submete trabalho. **Furo achado na sabotagem do
ciclo 6**, escrita contra o detector já alargado no ciclo 6 (F9-C6 §3)."""

RECEPTORES_DE_OCUPACAO = ("busy", "ocupad", "ocupac", "registry", "registro_de_ocupacao")
ASSINATURA_DO_REGISTRO = ("loses_work", "cancellable")
"""Como se prova que um `X.register(...)` é o `BusyRegistry` -- pelo receptor ou pela assinatura.

**A regra antiga aceitava qualquer chamada com `register` ou `registrar` no nome**, e o crítico
marcou uma thread crua como REGISTRADA pondo um `self._registrar_atalho_de_teclado()` na mesma
função. `qt/` tem hoje `self.historico.registrar`, `self._historico.registrar` e
`self._mapa.registrar`: três `registrar` sem relação nenhuma com ocupação."""

PROFUNDIDADE_DO_AJUDANTE = 3
"""Quantos níveis de ajudante se seguem, dentro do mesmo módulo, atrás da prova de registro.

A Galeria e a aba de Texto registram por `self._registrar_ocupado`, que chama
`self._busy.register`. Exigir a chamada literal empurraria para copiar o registro; aceitar o
nome aceita `historico.registrar`. Seguir a **definição** resolve os dois."""


def _termo_final(no: ast.expr, apelidos: dict[str, str] | None = None) -> str:
    """O último termo da expressão, com o índice descascado (F9-C8, forma a).

    `FABRICAS["fundo"](target=…)` tem `ast.unparse` igual a `FABRICAS['fundo']`, que não é nome
    nenhum: o termo passa a ser o do contêiner."""
    while isinstance(no, ast.Subscript):
        no = no.value
    termo = ast.unparse(no).rsplit(".", 1)[-1]
    return (apelidos or {}).get(termo, termo)


def _apelidos(arvore: ast.AST) -> dict[str, str]:
    """A tabela `import ... as ...` do arquivo: nome local -> nome verdadeiro.

    `from threading import Thread as T` faz `T(...)` ter termo final `T`, e `class _Derivada(T)`
    faz a herança perder o rastro pelo mesmo motivo. Duas das oito formas da sabotagem do ciclo 6
    passaram por aqui. `import threading as th` já era visto -- `th.Thread` tem `Thread` como
    termo final --; o que escapava era o apelido **da classe**."""
    tabela: dict[str, str] = {}
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Import, ast.ImportFrom)):
            for nome in no.names:
                if nome.asname and nome.asname not in {"_", "__"}:
                    verdadeiro = nome.name.rsplit(".", 1)[-1]
                    if verdadeiro != nome.asname:
                        tabela[nome.asname] = verdadeiro
        elif isinstance(no, ast.Assign) and isinstance(no.value, (ast.Name, ast.Attribute)):
            # **Apelido por atribuição** (F9-C7 §4.3, forma a): `Fabrica = threading.Thread`.
            # Só nome nu: `tarefa = Tarefa(...)` é instância, e tratá-la como apelido de classe
            # faria `tarefa.qualquer_coisa()` virar construção de thread.
            verdadeiro = ast.unparse(no.value).rsplit(".", 1)[-1]
            for alvo in no.targets:
                if (
                    isinstance(alvo, ast.Name)
                    and alvo.id not in {"_", "__"}
                    and verdadeiro != alvo.id
                ):
                    tabela.setdefault(alvo.id, verdadeiro)
        elif isinstance(no, ast.Assign) and isinstance(no.value, (ast.Dict, ast.List, ast.Tuple)):
            # **Contêiner literal de classes** (F9-C8, forma a). Só entra se algum elemento for
            # uma classe da semente: um dicionário de funções continua invisível.
            dentro = (
                list(no.value.values) if isinstance(no.value, ast.Dict) else list(no.value.elts)
            )
            for item in dentro:
                if not isinstance(item, (ast.Name, ast.Attribute)):
                    continue
                classe = ast.unparse(item).rsplit(".", 1)[-1]
                if classe in CLASSES_DE_THREAD:
                    for alvo in no.targets:
                        if isinstance(alvo, ast.Name) and alvo.id not in {"_", "__"}:
                            tabela.setdefault(alvo.id, classe)
    return tabela


def _classes_de_thread(arquivos: Sequence[Path] = ()) -> set[str]:
    """`CLASSES_DE_THREAD` mais toda subclasse delas declarada na interface, em ponto fixo."""
    alvos = list(arquivos) or (
        sorted((RAIZ / "src" / "chess_diagram_ocr" / "qt").glob("*.py"))
        + sorted((RAIZ / "src" / "chess_diagram_ocr" / "ui").glob("*.py"))
    )
    nomes = set(CLASSES_DE_THREAD)
    bases: dict[str, set[str]] = {}
    for caminho in alvos:
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        apelidos = _apelidos(arvore)
        for no in ast.walk(arvore):
            if isinstance(no, ast.ClassDef):
                bases.setdefault(no.name, set()).update(
                    _termo_final(b, apelidos) for b in no.bases
                )
    mudou = True
    while mudou:
        mudou = False
        for classe, delas in bases.items():
            if classe not in nomes and delas & nomes:
                nomes.add(classe)
                mudou = True
    return nomes


def _forma_de_fundo(
    no: ast.Call, classes: set[str], apelidos: dict[str, str] | None = None
) -> str:
    """Como esta chamada abre trabalho de fundo, ou vazio.

    Cinco regras: construção (subclasse, import direto, apelido de import, apelido por
    atribuição e contêiner literal), submissão a uma linha já aberta, submissão a um pool por um
    método que só conta com receptor de pool, classe guardada num `partial`, e programa externo
    largado a correr. A régua é a gêmea de `caissa.ui.audit.progresso.forma_de_fundo`, e as duas
    mudam juntas: era o ponto cego que o crítico do ciclo 5 nomeou."""
    termo = _termo_final(no.func, apelidos)
    if termo in classes:
        return f"constroi {ast.unparse(no.func)}"
    if termo in METODOS_DE_SUBMISSAO:
        return f"submete por {ast.unparse(no.func)}"
    if termo in METODOS_DE_POOL:
        texto = ast.unparse(no.func)
        receptor = texto.rsplit(".", 1)[0].lower() if "." in texto else ""
        if any(palavra in receptor for palavra in RECEPTORES_DE_POOL) and (
            no.args or termo != "start"
        ):
            return f"submete por {texto}"
    if termo in EMBRULHOS_DE_CHAMADA and no.args and _termo_final(no.args[0], apelidos) in classes:
        return f"embrulha {ast.unparse(no.args[0])} em {termo}"
    if termo in FUNCOES_DE_PROCESSO_EXTERNO:
        return f"larga um programa externo por {ast.unparse(no.func)}"
    if isinstance(no.func, ast.Call) and _termo_final(no.func.func, apelidos) == "getattr":
        pedido = no.func.args[1] if len(no.func.args) > 1 else None
        if isinstance(pedido, ast.Constant) and str(pedido.value) in classes:
            return f"constroi {ast.unparse(no.func)}"
    return ""


def _threads_por_funcao(
    caminho: Path, classes: set[str] | None = None
) -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef | None]]:
    """Cada operação de fundo aberta no arquivo, com a função que a dispara.

    **Duas regras, e a segunda existe porque a primeira não basta.** Construção de classe de
    thread -- inclusive subclasse e import direto -- e submissão a uma linha já aberta, que não
    constrói classe nenhuma no ponto de chamada. Ver `CLASSES_DE_THREAD` para o que a régua
    antiga deixava passar.

    Uma linha conta uma vez: `ThreadPoolExecutor(1).submit(f)` casa com as duas regras e é a
    mesma thread."""
    classes = classes if classes is not None else _classes_de_thread()
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    apelidos = _apelidos(arvore)
    pais: dict[ast.AST, ast.AST] = {}
    for no in ast.walk(arvore):
        for filho in ast.iter_child_nodes(no):
            pais[filho] = no

    achados = []
    vistas: set[int] = set()
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call) or not _forma_de_fundo(no, classes, apelidos):
            continue
        if no.lineno in vistas:
            continue
        vistas.add(no.lineno)
        atual: ast.AST | None = pais.get(no)
        while atual is not None and not isinstance(atual, (ast.FunctionDef, ast.AsyncFunctionDef)):
            atual = pais.get(atual)
        achados.append((f"{caminho.name}:{no.lineno}", atual))
    return achados


def _prova_de_registro(no: ast.Call) -> bool:
    """Se **esta** chamada é um registro no `BusyRegistry`, pelo receptor ou pela assinatura."""
    if _termo_final(no.func) != "register":
        return False
    texto = ast.unparse(no.func)
    receptor = texto.rsplit(".", 1)[0].lower() if "." in texto else ""
    if any(palavra in receptor for palavra in RECEPTORES_DE_OCUPACAO):
        return True
    return bool({p.arg for p in no.keywords if p.arg} & set(ASSINATURA_DO_REGISTRO))


def _funcoes_do_modulo(caminho: Path) -> dict[str, ast.AST]:
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    return {
        no.name: no
        for no in ast.walk(arvore)
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _registra(
    funcao: ast.FunctionDef | ast.AsyncFunctionDef,
    funcoes: dict[str, ast.AST] | None = None,
    *,
    profundidade: int = PROFUNDIDADE_DO_AJUDANTE,
    vistos: frozenset[str] = frozenset(),
) -> bool:
    """A função registra a ocupação -- ela mesma, ou por um ajudante **deste** módulo.

    O nome sozinho não vale mais: a Galeria e a aba de Texto continuam registrando por
    `_registrar_ocupado`, e ele prova registro porque o **corpo** dele prova. Um
    `self._registrar_atalho_de_teclado()` não prova nada, e era o falso positivo que o crítico
    do ciclo 5 plantou (forma f)."""
    funcoes = funcoes if funcoes is not None else {}
    for no in ast.walk(funcao):
        if not isinstance(no, ast.Call):
            continue
        if _prova_de_registro(no):
            return True
        if profundidade <= 0:
            continue
        nome = _termo_final(no.func)
        ajudante = funcoes.get(nome)
        if ajudante is None or nome in vistos or ajudante is funcao:
            continue
        if _registra(ajudante, funcoes, profundidade=profundidade - 1, vistos=vistos | {nome}):
            return True
    return False


class RegistryTests(unittest.TestCase):
    def test_sem_operacao_nao_ha_por_que_perguntar(self) -> None:
        registro = BusyRegistry()
        self.assertFalse(registro.is_busy)
        self.assertEqual(registro.close_warning(), "")

    def test_soltar_o_token_esvazia_o_registro(self) -> None:
        registro = BusyRegistry()
        token = registro.register("treino do modelo", loses_work=True)
        self.assertTrue(registro.is_busy)

        token.release()

        self.assertFalse(registro.is_busy)
        self.assertEqual(registro.close_warning(), "")

    def test_o_token_funciona_como_contexto(self) -> None:
        registro = BusyRegistry()
        with registro.register("varredura", loses_work=False):
            self.assertTrue(registro.is_busy)
        self.assertFalse(registro.is_busy)

    def test_o_aviso_nomeia_a_operacao_e_o_que_se_perde(self) -> None:
        registro = BusyRegistry()
        registro.register("treino do modelo", loses_work=True, detail="época 3 de 8")

        aviso = registro.close_warning()

        self.assertIn("treino do modelo", aviso)
        self.assertIn("época 3 de 8", aviso)
        self.assertIn("descarta o progresso", aviso)

    def test_operacao_com_checkpoint_proprio_nao_promete_perda(self) -> None:
        """A exportação tem parcial (S-24): fechar custa tempo, não trabalho.

        Dizer "você vai perder tudo" quando não vai treina o usuário a ignorar o aviso, e aí
        ele ignora também o do treino, que é verdadeiro.
        """
        registro = BusyRegistry()
        registro.register("exportação para PGN", loses_work=False, detail="livro.pdf")

        aviso = registro.close_warning()

        self.assertIn("exportação para PGN", aviso)
        self.assertNotIn("descarta o progresso", aviso)
        self.assertIn("já está salvo", aviso)

    def test_duas_operacoes_aparecem_as_duas_e_a_perda_e_nomeada(self) -> None:
        registro = BusyRegistry()
        registro.register("exportação para PGN", loses_work=False)
        registro.register("treino do modelo", loses_work=True)

        aviso = registro.close_warning()

        self.assertIn("2 operações", aviso)
        self.assertIn("exportação para PGN", aviso)
        self.assertIn("descarta o progresso de: treino do modelo", aviso)

    def test_o_detalhe_pode_ser_atualizado_durante_a_operacao(self) -> None:
        registro = BusyRegistry()
        token = registro.register("treino do modelo", loses_work=True, detail="época 1 de 8")

        token.update("época 5 de 8")

        self.assertIn("época 5 de 8", registro.close_warning())

    def test_a_operacao_que_sabe_o_total_publica_a_fracao(self) -> None:
        """O que faz a barra do rodapé ser determinada (S-164).

        O número vem separado do texto de propósito: derivar a fração de "época 3 de 8" exigiria
        interpretar a frase, e a frase é escrita para ser lida, não parseada.
        """
        registro = BusyRegistry()
        token = registro.register("treino do modelo", loses_work=True, total=8)

        token.update("época 2 de 8", feito=2, total=8)

        self.assertAlmostEqual(registro.running()[0].fracao, 0.25)

    def test_sem_total_conhecido_nao_ha_fracao_a_prometer(self) -> None:
        """A busca por nome descobre o tamanho enquanto lê; ali uma fração seria inventada."""
        registro = BusyRegistry()
        registro.register("busca por nome na base", loses_work=False, detail="3 par(es)")
        self.assertIsNone(registro.running()[0].fracao)

    def test_a_atualizacao_de_detalhe_nao_apaga_o_total(self) -> None:
        """`replace` e não reconstruir campo a campo: o campo esquecido voltaria ao padrão."""
        registro = BusyRegistry()
        token = registro.register("exportação para PGN", loses_work=False, total=402)

        token.update("página 120 de 402", feito=120)

        operacao = registro.running()[0]
        self.assertEqual(operacao.total, 402)
        self.assertAlmostEqual(operacao.fracao, 120 / 402)

    def test_a_contagem_que_passa_do_total_nao_estoura_a_barra(self) -> None:
        """Retomar uma varredura pode relê uma página; barra além do fim seria o sintoma."""
        registro = BusyRegistry()
        token = registro.register("varredura da Galeria", loses_work=False, total=10)
        token.update("página 12 de 10", feito=12, total=10)
        self.assertEqual(registro.running()[0].fracao, 1.0)

    def test_o_observador_e_avisado_ao_registrar_e_ao_soltar(self) -> None:
        """**Quem quer saber já, sabe já** (F9-C4).

        O rodapé lia o registro por relógio, a cada 400 ms, e a zona de mensagem é escrita por
        sinal no instante em que a operação começa. As duas zonas discordavam por até 400 ms, e
        isso está em `benchmarks/reports/ui/c4/c4_claro_1280x800_dataset.png`: "Lendo o dataset…"
        com a barra escondida e o `Cancelar` cinzento.
        """
        registro = BusyRegistry()
        avisos: list[int] = []
        registro.observe(lambda: avisos.append(len(registro.running())))

        ficha = registro.register("leitura", loses_work=False)
        self.assertEqual(avisos, [1], "registrar não avisou")
        ficha.release()
        self.assertEqual(avisos, [1, 0], "soltar não avisou")

    def test_o_aviso_do_detalhe_so_sai_quando_o_detalhe_muda(self) -> None:
        """A barra determinada é atualizada por callback de progresso, tique a tique.

        Avisar num tique que não mudou nada faria o rodapé repintar sem ter o que dizer -- e o
        `aplicar_ocupacao` já evita reescrever a faixa pelo mesmo motivo.
        """
        registro = BusyRegistry()
        ficha = registro.register("varredura", loses_work=True, total=10)
        avisos: list[str] = []
        registro.observe(lambda: avisos.append("mudou"))

        ficha.update("página 3", feito=3, total=10)
        self.assertEqual(avisos, ["mudou"])
        ficha.update("página 3", feito=3, total=10)
        self.assertEqual(avisos, ["mudou"], "um tique idêntico avisou")

    def test_um_observador_que_levanta_nao_derruba_quem_registrou(self) -> None:
        """Mesmo contrato de `request_cancel`: avisar é best-effort.

        Um rodapé já destruído levanta `RuntimeError` no Qt, e a operação que estava começando
        não pode morrer por causa disso.
        """
        registro = BusyRegistry()
        registro.observe(lambda: (_ for _ in ()).throw(RuntimeError("rodapé morto")))
        vistos: list[str] = []
        registro.observe(lambda: vistos.append("segundo"))

        with self.assertLogs("chess_diagram_ocr.ui.busy", level="ERROR"):
            ficha = registro.register("leitura", loses_work=False)
        self.assertEqual(len(registro.running()), 1)
        self.assertEqual(vistos, ["segundo"], "o segundo observador foi perdido pelo erro do primeiro")
        ficha.release()

    def test_pedir_cancelamento_avisa_so_quem_sabe_parar(self) -> None:
        registro = BusyRegistry()
        parado = threading.Event()
        registro.register("treino do modelo", loses_work=True, cancellable=True, cancel=parado.set)
        registro.register("outra coisa", loses_work=True)

        avisadas = registro.request_cancel()

        self.assertEqual(avisadas, 1)
        self.assertTrue(parado.is_set())

    def test_cancellable_sem_callback_nao_promete_o_que_nao_cumpre(self) -> None:
        registro = BusyRegistry()
        registro.register("treino do modelo", loses_work=True, cancellable=True)
        self.assertFalse(registro.running()[0].cancellable)

    def test_registrar_de_varias_threads_nao_perde_operacao(self) -> None:
        """Quem registra é a thread de trabalho; quem lê é a da interface."""
        registro = BusyRegistry()
        largada = threading.Event()

        def _trabalha(indice: int) -> None:
            largada.wait()
            registro.register(f"op {indice}", loses_work=False)

        threads = [threading.Thread(target=_trabalha, args=(i,)) for i in range(16)]
        for thread in threads:
            thread.start()
        largada.set()
        for thread in threads:
            thread.join()

        self.assertEqual(len(registro.running()), 16)


SABOTAGEM_C6 = textwrap.dedent(
    """
    import asyncio
    import multiprocessing
    import threading
    from concurrent.futures import ProcessPoolExecutor
    from threading import Thread as T


    class _Derivada(T):
        def run(self):
            return None


    class LeitorSabotadorC6:
        def g_alias_de_import(self):
            T(target=self._ler, daemon=True).start()

        def h_modulo_aliasado(self):
            import threading as th
            th.Thread(target=self._ler).start()

        def i_processo(self):
            multiprocessing.Process(target=self._ler).start()

        def j_pool_de_processo(self):
            ProcessPoolExecutor(max_workers=1).submit(self._ler)

        def k_executor_do_asyncio(self):
            asyncio.get_event_loop().run_in_executor(None, self._ler)

        def l_subclasse_de_alias(self):
            _Derivada().start()

        def m_qthreadpool(self):
            QThreadPool.globalInstance().start(self._tarefa)

        def n_registro_de_outro_modulo(self):
            self._mapa.registrar("x")
            threading.Thread(target=self._ler).start()

        def _ler(self):
            return None
    """
)
"""**As oito formas do ciclo 6**, escritas contra o detector já alargado -- três passaram.

`g` e `l` passavam pelo apelido de import (`Thread as T`, e a herança que segue o nome da base);
`m` passava porque `QThreadPool.start` não constrói classe nenhuma no ponto de chamada e não se
chama `submit`. As outras cinco -- `Process`, `ProcessPoolExecutor.submit`,
`run_in_executor`, o `threading as th` e o `registrar` de outro módulo -- já eram vistas, e
ficam aqui como catraca."""


SABOTAGEM_C8 = textwrap.dedent(
    '''
    import asyncio
    import os
    import threading
    from functools import partial
    from multiprocessing.pool import ThreadPool

    from PyQt6.QtCore import QThreadPool


    class SabotadorC8:
        FABRICA = threading.Thread
        FABRICAS = {"fundo": threading.Thread}

        def a_fabrica_num_dicionario(self):
            self.FABRICAS["fundo"](target=self._ler, daemon=True).start()

        def b_thread_pool_do_multiprocessing(self):
            ThreadPool(4).close()

        def c_create_task(self):
            asyncio.create_task(self._corrotina())

        def d_run_coroutine_threadsafe(self):
            asyncio.run_coroutine_threadsafe(self._corrotina(), self._laco)

        def e_try_start_no_pool_do_qt(self):
            QThreadPool.globalInstance().tryStart(self._ler)

        def f_apelido_de_atributo_de_classe(self):
            self.FABRICA(target=self._ler, daemon=True).start()

        def g_startfile(self):
            os.startfile("relatorio.pdf")

        def h_getattr_no_modulo(self):
            getattr(threading, "Thread")(target=self._ler, daemon=True).start()

        def n1_relogio_da_interface(self):
            self._relogio.start(250)

        def n2_map_comum(self):
            return list(map(str, range(10)))

        def n3_partial_comum(self):
            return partial(self._ler_de, 1)

        async def _corrotina(self):
            return None

        def _ler(self):
            return None

        def _ler_de(self, i):
            return i
    '''
)
"""**As oito formas do ciclo 8**, escritas contra o detector alargado no mesmo ciclo -- sete
passaram na primeira execução, e a oitava (`f`) só foi vista porque o apelido por atribuição já
tinha entrado por causa da sabotagem do crítico do ciclo 7.

O que faltava, forma a forma: o índice escondendo a classe (`FABRICAS["fundo"]`), o
`multiprocessing.pool.ThreadPool` cujo termo final não é `Pool`, as três do `asyncio` que põem
uma corrotina a correr, o `tryStart` irmão do `start` do `QThreadPool`, o `os.startfile` que
larga um programa externo, e a classe buscada por `getattr`.

**Os três `n*` são controles negativos e não podem aparecer**: um relógio da interface, um `map`
comum e um `partial` comum. Um portão que grita demais deixa de ser lido, que é a outra forma de
ficar cego -- e é por isso que `map` não entrou em `METODOS_DE_SUBMISSAO`, só em
`METODOS_DE_POOL`."""


class ThreadsDeclaradasTests(unittest.TestCase):
    """Toda thread da interface está no registro, ou está na lista de exceções (S-112).

    A S-60 construiu o registro e o ligou às duas operações longas que existiam então. Um ano
    de itens depois havia **doze** threads e **dois** registros: ficavam de fora a varredura da
    Galeria, a da fila de revisão, a busca por nome, a detecção de duplicatas e -- a mais cara
    do programa, ~56 min medidos na Fase 13 -- a busca por posição. Fechar a janela aos 50
    minutos descartava a passada sem uma palavra.

    O que trava a regressão não é a contagem, é a **exigência**: uma thread nova ou registra
    ou se declara, e as duas coisas obrigam quem a escreve a responder "o que se perde se a
    janela fechar agora?".
    """

    def test_toda_thread_da_ui_registra_ou_esta_declarada(self) -> None:
        faltando = []
        for caminho in ARQUIVOS_COM_THREAD:
            for onde, funcao in _threads_por_funcao(caminho):
                if funcao is None:
                    faltando.append(f"{onde}: fora de função, sem onde registrar")
                    continue
                if (caminho.name, funcao.name) in SEM_REGISTRO or _registra(
                    funcao, _funcoes_do_modulo(caminho)
                ):
                    continue
                faltando.append(f"{onde} ({funcao.name})")

        self.assertEqual(
            faltando,
            [],
            "Thread nova sem registro. Ou ela chama `busy.register(...)` dizendo o que se "
            "perde ao fechar a janela, ou ela entra em SEM_REGISTRO com o motivo escrito.",
        )

    def test_a_lista_de_excecoes_nao_guarda_thread_que_nao_existe_mais(self) -> None:
        """Exceção que sobrevive ao worker que a justificava vira permissão em branco."""
        reais = {
            (caminho.name, funcao.name)
            for caminho in ARQUIVOS_COM_THREAD
            for _onde, funcao in _threads_por_funcao(caminho)
            if funcao is not None
        }
        self.assertEqual(sorted(set(SEM_REGISTRO) - reais), [])

    def test_a_lista_de_excecoes_nao_guarda_quem_ja_registra(self) -> None:
        """Declarada **e** registrada é uma declaração que sobreviveu ao próprio motivo (F9-C3).

        A irmã acima impede a exceção de sobreviver ao worker; esta impede que ela sobreviva ao
        **registro**. Sem ela, `marcas.pedir` e `painel_do_dataset._reler_agora` podiam passar a
        registrar e continuar na lista para sempre -- e a lista deixaria de dizer quem está de
        fora, que é a única coisa que ela existe para dizer.
        """
        registradas = [
            f"{caminho.name}:{funcao.name}"
            for caminho in ARQUIVOS_COM_THREAD
            for _onde, funcao in _threads_por_funcao(caminho)
            if funcao is not None
            and (caminho.name, funcao.name) in SEM_REGISTRO
            and _registra(funcao, _funcoes_do_modulo(caminho))
        ]
        self.assertEqual(
            registradas,
            [],
            "Estas threads registram e ainda estão em FORA_DO_REGISTRO. Tire-as da tabela de "
            "`ui/busy.py`: a declaração serve para quem fica **de fora** do registro.",
        )

    def test_cada_excecao_diz_por_que(self) -> None:
        """Uma lista de nomes seria uma lista de nomes; o que vale é o motivo ao lado."""
        for chave, motivo in SEM_REGISTRO.items():
            self.assertGreater(len(motivo), 30, f"{chave} está na lista sem justificativa")

    def test_a_busca_por_posicao_pede_confirmacao_explicita(self) -> None:
        """O critério de aceite da S-112, no vocabulário do registro.

        A passada é descartada inteira -- meia base lida dá contagens que não valem --, e é a
        única das cinco novas cujo `loses_work` é verdadeiro por não ter nada em disco a
        recuperar.
        """
        registro = BusyRegistry()
        registro.register("busca por posição na base", loses_work=True, detail="8.034 posição(ões)")

        aviso = registro.close_warning()

        self.assertIn("busca por posição na base", aviso)
        self.assertIn("descarta o progresso de: busca por posição na base", aviso)
        self.assertIn("Fechar mesmo assim?", aviso)


if __name__ == "__main__":
    unittest.main()


SABOTAGEM = textwrap.dedent(
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from threading import Thread


    class LeitorSabotador:
        def a_thread_crua(self):
            threading.Thread(target=self._ler_tudo, daemon=True).start()

        def b_import_direto(self):
            Thread(target=self._ler_tudo, daemon=True).start()

        def c_pool(self):
            ThreadPoolExecutor(max_workers=1).submit(self._ler_tudo)

        def d_timer(self):
            threading.Timer(0.0, self._ler_tudo).start()

        def e_subclasse(self):
            _MinhaThread().start()

        def f_registro_de_mentira(self):
            self._registrar_atalho_de_teclado()
            threading.Thread(target=self._ler_tudo, daemon=True).start()

        def g_registra_de_verdade(self):
            self._busy.register("ler tudo", loses_work=False)
            threading.Thread(target=self._ler_tudo, daemon=True).start()

        def h_registra_por_ajudante(self):
            self._registrar_ocupado("ler tudo")
            threading.Thread(target=self._ler_tudo, daemon=True).start()

        def _registrar_ocupado(self, nome):
            return self._busy.register(nome, loses_work=False)

        def _registrar_atalho_de_teclado(self):
            return None

        def _ler_tudo(self):
            return None


    class _MinhaThread(threading.Thread):
        def run(self):
            return None
    """
)
"""**As seis formas que o crítico do ciclo 5 plantou**, mais duas que registram de verdade.

Nenhuma lista de grafias literais pega as seis; e um detector que passasse a gritar em tudo
pegaria também as duas últimas, que estão certas. As oito juntas medem as duas pontas."""


class SabotagemDoDetectorTests(unittest.TestCase):
    """**A prova de vida do detector**, e ela é a exigência do §9.3 do ciclo 5.

    Um portão novo sem sabotagem é uma promessa. O do ciclo 5 dizia "0 invisíveis" e era
    verdade sobre o produto -- e falso sobre o próximo código a ser escrito: das seis operações
    de fundo plantadas pelo crítico, o detector achou **1**, marcou **1** como REGISTRADA
    porque *qualquer* chamada com `registrar` no nome contava, e não viu **4**.

    Estes testes plantam as mesmas seis num arquivo temporário e exigem 6 de 6 -- e mais duas
    que registram de verdade, para que "alargar" não vire "acusar todo mundo".
    """

    def _planta(self, pasta: str) -> Path:
        caminho = Path(pasta) / "sabotagem.py"
        caminho.write_text(SABOTAGEM, encoding="utf-8")
        return caminho

    def test_as_seis_formas_de_abrir_thread_sao_todas_detectadas(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = self._planta(pasta)
            classes = _classes_de_thread([caminho])
            achadas = _threads_por_funcao(caminho, classes)
        donas = sorted(funcao.name for _onde, funcao in achadas if funcao is not None)
        self.assertEqual(
            [
                "a_thread_crua",
                "b_import_direto",
                "c_pool",
                "d_timer",
                "e_subclasse",
                "f_registro_de_mentira",
                "g_registra_de_verdade",
                "h_registra_por_ajudante",
            ],
            donas,
            "o detector deixou de ver uma forma de abrir thread",
        )

    def test_as_formas_novas_do_ciclo_6_tambem_sao_detectadas(self) -> None:
        """**A segunda prova de vida** -- sabotagem escrita contra o detector já alargado.

        Um detector que só passa na sabotagem que motivou o conserto não foi testado, foi
        ajustado. Fechadas as seis formas do ciclo 5, escrevi oito novas e rodei: **três
        passaram** -- `from threading import Thread as T`, `class _Derivada(T)` e
        `QThreadPool.globalInstance().start(tarefa)`. `_apelidos` e `RECEPTORES_DE_POOL` são o
        conserto; as outras cinco já eram vistas e ficam aqui para não regredirem."""
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "sabotagem_c6.py"
            caminho.write_text(SABOTAGEM_C6, encoding="utf-8")
            achadas = _threads_por_funcao(caminho, _classes_de_thread([caminho]))
        donas = sorted(funcao.name for _onde, funcao in achadas if funcao is not None)
        self.assertEqual(
            [
                "g_alias_de_import",
                "h_modulo_aliasado",
                "i_processo",
                "j_pool_de_processo",
                "k_executor_do_asyncio",
                "l_subclasse_de_alias",
                "m_qthreadpool",
                "n_registro_de_outro_modulo",
            ],
            donas,
            "o detector deixou de ver uma forma de abrir thread",
        )

    def test_as_formas_novas_do_ciclo_8_tambem_sao_detectadas(self) -> None:
        """**A terceira prova de vida** -- sabotagem escrita contra o detector do ciclo 8.

        O crítico do ciclo 7 plantou oito formas contra o detector do ciclo 6 e **sete
        passaram**; fechadas essas, escrevi mais oito e **sete passaram de novo**. É a razão de a
        catraca existir: um detector que só passa na sabotagem que motivou o conserto não foi
        testado, foi ajustado.

        Cada forma tem de aparecer **no nome da função que a abre**. Era a segunda metade da
        queixa do crítico: `moveToThread` e `pool.map` só apareciam pela construção que o
        `__init__` fazia, e uma linha dizendo `__init__ constroi QThread` não diz que
        `e_move_to_thread` é uma operação de fundo."""
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "sabotagem_c8.py"
            caminho.write_text(SABOTAGEM_C8, encoding="utf-8")
            achadas = _threads_por_funcao(caminho, _classes_de_thread([caminho]))
        donas = sorted(funcao.name for _onde, funcao in achadas if funcao is not None)
        self.assertEqual(
            [
                "a_fabrica_num_dicionario",
                "b_thread_pool_do_multiprocessing",
                "c_create_task",
                "d_run_coroutine_threadsafe",
                "e_try_start_no_pool_do_qt",
                "f_apelido_de_atributo_de_classe",
                "g_startfile",
                "h_getattr_no_modulo",
            ],
            donas,
            "o detector deixou de ver uma forma de abrir trabalho de fundo",
        )

    def test_os_controles_negativos_do_ciclo_8_nao_sao_acusados(self) -> None:
        """O outro lado da mesma sabotagem: o relógio, o `map` e o `partial` comuns.

        Sem este teste, alargar o detector é grátis -- e um portão que acusa `list(map(str, x))`
        deixa de ser lido, que é a outra forma de ficar cego. Os três estão no **mesmo** arquivo
        das oito formas de cima, então este teste e o anterior medem a mesma varredura."""
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "sabotagem_c8.py"
            caminho.write_text(SABOTAGEM_C8, encoding="utf-8")
            achadas = _threads_por_funcao(caminho, _classes_de_thread([caminho]))
        donas = {funcao.name for _onde, funcao in achadas if funcao is not None}
        for controle in ("n1_relogio_da_interface", "n2_map_comum", "n3_partial_comum"):
            self.assertNotIn(controle, donas, "o detector passou a gritar onde nao ha thread")

    def test_o_start_de_um_relogio_nao_e_thread(self) -> None:
        """A regra do `start` pede pool **e** argumento, senão ela acusa `qt/` inteiro.

        `self._relogio.start(250)` tem argumento e não é thread; `Tarefa(...).start()` é thread
        e já foi contada na construção. Portão que grita demais deixa de ser lido, que é a outra
        maneira de ficar cego."""
        fonte = textwrap.dedent(
            """
            class Painel:
                def ligar(self):
                    self._relogio.start(250)
                    self._animacao.start()
                    self._pool.start()
            """
        )
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "relogios.py"
            caminho.write_text(fonte, encoding="utf-8")
            achadas = _threads_por_funcao(caminho, _classes_de_thread([caminho]))
        self.assertEqual([], achadas)

    def test_uma_linha_conta_uma_thread_so(self) -> None:
        """`ThreadPoolExecutor(1).submit(f)` casa com as duas regras e é a mesma thread."""
        with tempfile.TemporaryDirectory() as pasta:
            caminho = self._planta(pasta)
            achadas = _threads_por_funcao(caminho, _classes_de_thread([caminho]))
        linhas = [onde for onde, _funcao in achadas]
        self.assertEqual(sorted(set(linhas)), sorted(linhas))

    def test_registrar_qualquer_coisa_nao_conta_como_registrar_ocupacao(self) -> None:
        """A forma (f): thread crua numa função que chama `_registrar_atalho_de_teclado`.

        A régua antiga marcava esta como REGISTRADA. O rodapé nunca a mostrou.
        """
        with tempfile.TemporaryDirectory() as pasta:
            caminho = self._planta(pasta)
            funcoes = _funcoes_do_modulo(caminho)
            achadas = _threads_por_funcao(caminho, _classes_de_thread([caminho]))
            registra = {
                funcao.name: _registra(funcao, funcoes)
                for _onde, funcao in achadas
                if funcao is not None
            }
        self.assertFalse(registra["f_registro_de_mentira"], "`registrar` qualquer virou registro")
        for nome in ("a_thread_crua", "b_import_direto", "c_pool", "d_timer", "e_subclasse"):
            self.assertFalse(registra[nome], f"{nome} não registra e foi dada como registrada")

    def test_quem_registra_de_verdade_continua_reconhecido(self) -> None:
        """A outra ponta: alargar o detector não pode acusar quem faz a coisa certa.

        Direto (`self._busy.register(...)`) e por ajudante (`self._registrar_ocupado`), que é
        como a Galeria e a aba de Texto registram hoje.
        """
        with tempfile.TemporaryDirectory() as pasta:
            caminho = self._planta(pasta)
            funcoes = _funcoes_do_modulo(caminho)
            achadas = _threads_por_funcao(caminho, _classes_de_thread([caminho]))
            registra = {
                funcao.name: _registra(funcao, funcoes)
                for _onde, funcao in achadas
                if funcao is not None
            }
        self.assertTrue(registra["g_registra_de_verdade"])
        self.assertTrue(registra["h_registra_por_ajudante"])

    def test_a_guarda_reprova_a_copia_sabotada_do_produto(self) -> None:
        """O teste que trava a regressão, rodado contra o arquivo plantado.

        É a mesma asserção de `test_toda_thread_da_ui_registra_ou_esta_declarada`, aplicada a um
        módulo que não registra nada -- e ela **tem** de falhar ali. Um portão que não sabe
        falhar não é portão, e este projeto já teve cinco que passaram cegos.
        """
        with tempfile.TemporaryDirectory() as pasta:
            caminho = self._planta(pasta)
            funcoes = _funcoes_do_modulo(caminho)
            faltando = [
                onde
                for onde, funcao in _threads_por_funcao(caminho, _classes_de_thread([caminho]))
                if funcao is not None
                and (caminho.name, funcao.name) not in SEM_REGISTRO
                and not _registra(funcao, funcoes)
            ]
        self.assertEqual(6, len(faltando), f"esperava 6 invisíveis, vieram {faltando}")


# ------------------------------------------------------- o portão de EXECUÇÃO (F9-C10)


def _origem_da_pilha(saltar: int = 1) -> tuple[str, str]:
    """`(arquivo, função)` de quem abriu o trabalho -- o primeiro quadro fora da biblioteca.

    **É o que faz `executor.submit(...)` ser atribuído a quem o chamou**, e não a
    `concurrent/futures/thread.py` -- a queixa literal do crítico do ciclo 7 contra a régua de
    AST: *"uma linha dizendo `__init__` constrói `QThread` não diz que `e_move_to_thread` é uma
    operação de fundo"*.

    `saltar` são os quadros do próprio vigia (o embrulho que chamou esta função). **Contados, e
    não filtrados por caminho**: o embrulho mora neste arquivo e o chamador de teste também, então
    pular "este arquivo" apagaria justamente a resposta -- foi o que a primeira forma desta função
    fez, e o teste de prova de vida devolveu `(desconhecido)`.
    """
    import inspect
    import sysconfig

    da_biblioteca = tuple(
        str(Path(caminho).resolve()).lower()
        for chave in ("stdlib", "platstdlib", "purelib", "platlib")
        if (caminho := sysconfig.get_paths().get(chave))
    )
    quadro = inspect.currentframe()
    for _ in range(saltar + 1):
        if quadro is None:
            return ("(desconhecido)", "(desconhecido)")
        quadro = quadro.f_back
    while quadro is not None:
        caminho = str(Path(quadro.f_code.co_filename).resolve()).lower()
        if not caminho.startswith(da_biblioteca) and "<" not in quadro.f_code.co_filename:
            return (Path(quadro.f_code.co_filename).name, quadro.f_code.co_name)
        quadro = quadro.f_back
    return ("(desconhecido)", "(desconhecido)")


class _Vigia:
    """Intercepta toda abertura de trabalho de fundo enquanto o bloco corre. Restaura tudo."""

    def __init__(self) -> None:
        self.aberturas: list[tuple[str, str]] = []
        self.registros: set[str] = set()
        self.fios: set[int] = set()
        self._desfazer: list[tuple[object, str, object]] = []

    def _remendar(self, alvo: object, nome: str, feitor) -> None:
        """Troca `alvo.nome` e guarda o **descritor** original, não o que `getattr` devolve.

        **A diferença quebrou três testes deste repositório, e é sutil.** Para uma classe do sip
        (`QThread`), `getattr(QThread, "start")` devolve um `builtin_function_or_method`
        **desligado da classe**; devolvê-lo por `setattr` deixa `QThread.start` com um objeto que
        já não sabe se ligar à instância, e a chamada seguinte morre com *"first argument of
        unbound method must have type 'QThread'"*. Quem restaura de verdade é
        `QThread.__dict__["start"]`, o `sip.methoddescriptor`.

        Achado por esta suíte: os três testes de `qt/trabalho.DeteccaoDeFundo` passaram a falhar
        **depois** de o vigia rodar no mesmo processo. Um instrumento que estraga o que mediu é
        pior que um que não mede -- e foi a régua gêmea que pegou, no portão do arnês também.
        """
        proprio = getattr(alvo, "__dict__", {}) or {}
        original = proprio.get(nome, getattr(alvo, nome, None))
        if original is None:
            return
        try:
            setattr(alvo, nome, feitor(getattr(alvo, nome)))
        except (TypeError, AttributeError):  # pragma: no cover - tipo de extensão fechado
            return
        self._desfazer.append((alvo, nome, original))

    def __enter__(self) -> "_Vigia":
        vigia = self

        def _thread_start(original):
            def dentro(self, *args, **kwargs):
                vigia.fios.add(id(self))
                vigia.aberturas.append(_origem_da_pilha())
                return original(self, *args, **kwargs)

            return dentro

        def _register(original):
            def dentro(self, nome, *args, **kwargs):
                vigia.registros.add(_origem_da_pilha()[0])
                return original(self, nome, *args, **kwargs)

            return dentro

        self._remendar(threading.Thread, "start", _thread_start)
        self._remendar(BusyRegistry, "register", _register)
        if TEM_PYQT:
            from PyQt6.QtCore import QThread, QThreadPool

            def _metodo(original):
                def dentro(*args, **kwargs):
                    vigia.aberturas.append(_origem_da_pilha())
                    return original(*args, **kwargs)

                return dentro

            self._remendar(QThread, "start", _metodo)
            self._remendar(QThreadPool, "start", _metodo)
        return self

    def __exit__(self, *_args: object) -> None:
        for alvo, nome, original in reversed(self._desfazer):
            setattr(alvo, nome, original)
        self._desfazer.clear()

    def sem_cobertura(self) -> list[str]:
        """As aberturas que não estão declaradas nem foram registradas pelo mesmo arquivo."""
        return [
            f"{arquivo}::{funcao}"
            for arquivo, funcao in self.aberturas
            if (arquivo, funcao) not in SEM_REGISTRO and arquivo not in self.registros
        ]


class PortaoDeExecucaoTests(unittest.TestCase):
    """A operação de fundo achada **vendo-a correr**, e não lendo a AST (F9-C10).

    **Por que esta classe existe ao lado de `SabotagemDoDetectorTests`.** A régua de AST perdeu a
    corrida: o crítico do ciclo 5 plantou 6 formas, o do 7 plantou 8, o construtor do 8 plantou 8,
    e o do **ciclo 9 plantou 8 novas -- das quais o detector pegou zero**. Cada rodada fecha as
    formas da anterior e a seguinte inventa outras; não há lista de padrões que termine.

    Uma thread que a AST não escreveu não existe para a AST; **uma thread que corre existe para o
    `threading`**. Aqui o teste conta `threading.enumerate()` antes e depois, intercepta os pontos
    de abertura, e exige que toda abertura esteja no `BusyRegistry` ou em `FORA_DO_REGISTRO` --
    que é, palavra por palavra, o alvo do §4.1 da crítica do ciclo 9.

    O portão do arnês é o mesmo (`caissa.ui.audit.execucao`), e ele roda contra três árvores de
    sabotagem executáveis. Este aqui é a **régua gêmea**: a lição do ciclo 5 é que o teste e o
    portão têm de mudar juntos, e por isso os dois existem.
    """

    @unittest.skipUnless(TEM_PYQT, MOTIVO)
    def test_nenhuma_abertura_da_janela_fica_sem_cobertura(self) -> None:
        """A janela viva, aba por aba: toda thread aberta registra ou está declarada."""
        import json

        from qt_app import aplicacao, descartar

        from chess_diagram_ocr.qt.janela import JanelaPrincipal

        app = aplicacao()
        antes = {id(fio) for fio in threading.enumerate()}
        with tempfile.TemporaryDirectory() as pasta:
            estado = Path(pasta) / "estado_do_teste.json"
            estado.write_text(json.dumps({"version": 6}), encoding="utf-8")
            with _Vigia() as vigia:
                janela = JanelaPrincipal(caminho_do_estado=estado)
                janela.show()
                for _ in range(4):
                    app.processEvents()
                for indice in range(janela.abas.count()):
                    janela.abas.setCurrentIndex(indice)
                    for _ in range(4):
                        app.processEvents()
                for _ in range(8):
                    app.processEvents()
                descartar(janela)
                nao_atribuidas = [
                    fio.name
                    for fio in threading.enumerate()
                    if id(fio) not in antes and id(fio) not in vigia.fios
                ]
        self.assertEqual([], vigia.sem_cobertura())
        self.assertEqual(
            [],
            nao_atribuidas,
            "nasceu uma thread que nenhum ponto interceptado explica -- ou o produto abriu "
            "trabalho por um caminho novo, ou esta régua precisa de um ponto a mais",
        )

    def test_a_regua_acusa_uma_thread_crua_de_arquivo_nao_declarado(self) -> None:
        """A prova de vida, e sem ela a asserção acima é "não achei nada".

        A thread é aberta **deste** arquivo, que não está em `FORA_DO_REGISTRO` e não registra --
        exatamente a forma que o §4.1 pede que o portão pegue, e que **oito de oito** formas do
        crítico do ciclo 9 usam sob outra sintaxe.
        """
        with _Vigia() as vigia:
            fio = threading.Thread(target=lambda: None, daemon=True)
            fio.start()
            fio.join(2.0)
        self.assertEqual(1, len(vigia.aberturas))
        self.assertEqual(
            ["test_busy.py::test_a_regua_acusa_uma_thread_crua_de_arquivo_nao_declarado"],
            vigia.sem_cobertura(),
        )

    def test_a_regua_fica_calada_quando_o_mesmo_arquivo_registra(self) -> None:
        """O outro lado: um portão que passasse a gritar seria a outra maneira de ficar cego."""
        registro = BusyRegistry()
        with _Vigia() as vigia:
            ficha = registro.register("uma operacao longa", loses_work=False)
            fio = threading.Thread(target=lambda: None, daemon=True)
            fio.start()
            fio.join(2.0)
            ficha.release()
        self.assertEqual(1, len(vigia.aberturas))
        self.assertEqual([], vigia.sem_cobertura())

    def test_a_regua_fica_calada_quando_nada_abre_trabalho(self) -> None:
        with _Vigia() as vigia:
            _ = [str(numero) for numero in range(10)]
        self.assertEqual([], vigia.aberturas)
        self.assertEqual([], vigia.sem_cobertura())

    def test_o_vigia_desfaz_o_remendo_ao_sair(self) -> None:
        """Um vigia que deixasse `Thread.start` remendado contaminaria a suíte inteira depois
        dele -- e este arquivo roda no meio de quatro mil e quinhentos testes."""
        antes = threading.Thread.start
        with _Vigia():
            self.assertIsNot(threading.Thread.start, antes)
        self.assertIs(threading.Thread.start, antes)

    @unittest.skipUnless(TEM_PYQT, MOTIVO)
    def test_o_qthread_restaurado_continua_chamavel(self) -> None:
        """**O `getattr` de uma classe do sip não devolve o que restaura ela.** Ver `_remendar`.

        Este é o teste que faltava quando três testes de `qt/trabalho.py` começaram a falhar por
        causa de um vigia que já tinha saído: o remendo era desfeito, e o que voltava para
        `QThread.start` era um método **desligado da classe**.
        """
        from PyQt6.QtCore import QThread

        with _Vigia():
            pass
        fio = QThread()
        try:
            fio.start()
            fio.quit()
            fio.wait(2000)
        finally:
            fio.deleteLater()

    def test_um_bloco_que_levanta_tambem_desfaz(self) -> None:
        antes = threading.Thread.start
        with self.assertRaises(RuntimeError), _Vigia():
            raise RuntimeError("a ação levantou")
        self.assertIs(threading.Thread.start, antes)

