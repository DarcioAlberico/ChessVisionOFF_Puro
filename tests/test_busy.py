"""O que se perde ao fechar a janela, decidido fora dela (S-60).

`app_tkinter._on_close` gravava o estado e chamava `root.destroy()` sem perguntar nada. As
oito threads do app são `daemon=True` e nenhuma é aguardada, então um treino de ~9 min por
época morria ali em silêncio -- e o treino não tinha cancelamento, então fechar a janela era
o único jeito de pará-lo.

Sem Tk aqui de propósito: a decisão de **o que dizer** é o conteúdo do item, e ela é
testável sem abrir janela.
"""

from __future__ import annotations

import threading
import unittest

from chess_diagram_ocr.ui.busy import BusyRegistry


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


if __name__ == "__main__":
    unittest.main()
