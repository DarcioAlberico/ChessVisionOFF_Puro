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
import threading
import unittest
from pathlib import Path

from chess_diagram_ocr.ui.busy import BusyRegistry

RAIZ = Path(__file__).resolve().parents[1]

ARQUIVOS_COM_THREAD = sorted((RAIZ / "src" / "chess_diagram_ocr" / "qt").glob("*.py"))
"""Onde a interface abre threads.

**Era `ui/` mais o `app_tkinter.py` até o corte (S-506).** Depois dele `ui/` não abre thread
nenhuma -- é a camada pura --, e quem as abre é `qt/`. Apontar a varredura para a pasta antiga
deixaria a guarda passando em verde sobre zero threads, que é o modo de falha que ela existe
para evitar: a S-60 cobriu as duas operações longas que existiam então e as dez seguintes
entraram em silêncio."""

SEM_REGISTRO = {
    ("janela.py", "_rodar"): (
        "Marcar os diagramas e reconhecer a página -- as duas passam por aqui. É o laço interno "
        "do programa, limitado por `max_boards`, e o que ele produz aparece na tela: quem fecha "
        "a janela durante ele está desistindo do resultado, não perdendo trabalho gravado."
    ),
    ("trabalho.py", "_comecar"): (
        "A detecção dos diagramas da página que acabou de aparecer (S-68), ao fundo e sem "
        "trancar nada. Ninguém a pediu, ela custa décimos de segundo, e o que produz é um "
        "conjunto de retângulos que a próxima visita à página refaz."
    ),
    ("painel_de_estudo.py", "analyse"): (
        "Uma avaliação do motor sobre a posição na tela (S-33). Segundos, e derivada: a "
        "posição continua lá para pedir de novo."
    ),
    ("busca_de_partidas.py", "buscar"): (
        "Uma consulta ao índice por nome (S-533): dezenas de milissegundos na gigabase, e até "
        "~1 s quando o filtro pede a posição corrente e ela relê dois mil candidatas. Ela sai da "
        "linha de eventos porque a janela não pode parar, e **não** entra no registro porque não "
        "há o que perder ao fechar: nada é gravado, e a mesma pergunta se refaz com um clique. É "
        "o oposto do índice (`indice_da_base.py`), que grava e por isso se registra."
    ),
}
"""As threads que **não** entram no registro, e por quê -- uma linha cada, e a lista é o item.

Perguntar "fechar mesmo assim?" por causa de uma análise de dois segundos treina o usuário a
responder "sim" sem ler, e aí ele responde "sim" também para a busca por posição, que custa
56 minutos. O registro só vale enquanto quem for avisado tiver motivo para parar.

**Uma thread nova em `qt/` falha a suíte até estar registrada ou declarada aqui.** É o que a S-60 não teve: ela cobriu as duas operações longas que existiam
então, e as dez que vieram depois entraram em silêncio."""


def _threads_por_funcao(caminho: Path) -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef | None]]:
    """Cada thread aberta no arquivo, com a função que a dispara.

    **Duas formas, e as duas contam.** `threading.Thread(...)` é a que veio do Tk; `Tarefa(...)`
    é o `QThread` de `qt/trabalho.py`, e ele existe porque uma thread do Qt tem de voltar por
    sinal e não por chamada direta. Contar só a primeira deixaria de fora justamente as
    operações que o porte passou a rodar pelo caminho novo -- inclusive a leitura da página, que
    é o laço interno do programa."""
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    pais: dict[ast.AST, ast.AST] = {}
    for no in ast.walk(arvore):
        for filho in ast.iter_child_nodes(no):
            pais[filho] = no

    achados = []
    for no in ast.walk(arvore):
        if not (isinstance(no, ast.Call) and ast.unparse(no.func) in ("threading.Thread", "Tarefa")):
            continue
        atual: ast.AST | None = pais.get(no)
        while atual is not None and not isinstance(atual, (ast.FunctionDef, ast.AsyncFunctionDef)):
            atual = pais.get(atual)
        achados.append((f"{caminho.name}:{no.lineno}", atual))
    return achados


def _registra(funcao: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """A função chama algo cujo nome fala em registrar -- `busy.register` ou `_registrar_ocupado`.

    O nome e não o objeto: a Galeria e a aba de Texto registram por um ajudante, porque as
    operações de cada uma dividem o mesmo ponto de saída, e exigir a chamada literal empurraria
    para copiar o registro três vezes.

    **`register` e `registrar`**: o ajudante do lado do Qt tem nome em português, e procurar só
    pelo inglês fazia a Galeria -- que registra -- ser acusada de não registrar.
    """
    for no in ast.walk(funcao):
        if isinstance(no, ast.Call):
            nome = ast.unparse(no.func).rsplit(".", 1)[-1]
            if "register" in nome or "registrar" in nome:
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
                if (caminho.name, funcao.name) in SEM_REGISTRO or _registra(funcao):
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
