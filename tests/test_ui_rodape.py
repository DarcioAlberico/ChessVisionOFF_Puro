"""O rodapé da janela: zona, severidade e expiração decididas fora do Tk (S-163).

A barra de status era um `ttk.Label` cru dentro do painel esquerdo. Cinco consequências, e as
cinco estão ditas como asserção aqui: ela não tinha severidade (erro, aviso e confirmação com a
mesma aparência), não tinha altura fixa, e o estado do documento -- livro, página, "3 de 5
salvo(s)" -- vivia espremido no fim da barra de zoom, que reflui.

A decisão é pura de propósito, como em `ui/busy.py`: "erro não expira" e "a página concluída fala
em verde" são afirmáveis sem abrir janela.
"""

from __future__ import annotations

import tkinter as tk
import unittest

from tk_root import raiz

from chess_diagram_ocr.ui import rodape, tokens
from chess_diagram_ocr.ui.busy import BusyRegistry


class SeveridadeTests(unittest.TestCase):
    def test_a_frase_de_falha_nao_fica_cinza_por_esquecimento(self) -> None:
        """O piso da inferência: 60 chamadores escrevem frase pronta e nenhum declara severidade."""
        for frase in (
            "Falha no OCR.",
            "Não foi possível abrir a imagem.",
            "CSV inválido: linha 12.",
            "PDF corrompido.",
        ):
            with self.subTest(frase=frase):
                self.assertEqual(rodape.severidade_de(frase), rodape.ERRO)

    def test_o_que_pede_um_passo_antes_e_aviso_e_nao_erro(self) -> None:
        """"Abra um PDF primeiro" não é falha do programa: é a resposta de que falta um passo."""
        self.assertEqual(rodape.severidade_de("Abra um PDF primeiro."), rodape.AVISO)
        self.assertEqual(rodape.severidade_de("⚠ 3 amostra(s) de treino desta página"), rodape.AVISO)

    def test_a_confirmacao_do_trabalho_feito_e_informacao(self) -> None:
        self.assertEqual(rodape.severidade_de("Exemplo salvo: samples/0012_1.png"), rodape.INFORMACAO)
        self.assertEqual(rodape.severidade_de(""), rodape.INFORMACAO, "rodapé vazio não é alarme")

    def test_erro_ganha_de_aviso_quando_a_frase_tem_as_duas_marcas(self) -> None:
        """"Não foi possível encontrar o modelo" tem marca das duas listas, e é erro."""
        self.assertEqual(rodape.severidade_de("Não foi possível encontrar o modelo."), rodape.ERRO)

    def test_erro_nao_expira_e_os_outros_dois_expiram(self) -> None:
        """Um erro que ninguém leu é um erro que não aconteceu -- ele sai quando for substituído."""
        self.assertIsNone(rodape.expira_em_ms(rodape.ERRO))
        for severidade in (rodape.INFORMACAO, rodape.AVISO):
            with self.subTest(severidade=severidade):
                prazo = rodape.expira_em_ms(severidade)
                self.assertIsNotNone(prazo)
                self.assertGreater(prazo, 10_000, "menos que isso apaga a mensagem antes da olhada")

    def test_severidade_escrita_errada_levanta_em_vez_de_cair_no_padrao(self) -> None:
        """Mesma disciplina de `tokens.cor`: cair no padrão viraria erro que expira em silêncio."""
        with self.assertRaises(KeyError):
            rodape.expira_em_ms("URGENTE")

    def test_cada_severidade_tem_papel_de_cor_e_os_tres_passam_em_contraste(self) -> None:
        """São papéis de **texto**: o âmbar da marcação reprovaria aqui, e por isso não é ele."""
        fundo = tokens.RESERVA[tokens.SUPERFICIE_PADRAO]
        for severidade in rodape.SEVERIDADES:
            with self.subTest(severidade=severidade):
                papel = rodape.PAPEL_DE_TEXTO[severidade]
                razao = tokens.razao_de_contraste(tokens.RESERVA[papel], fundo)
                self.assertGreaterEqual(razao, tokens.AA_TEXTO, f"{papel} reprova como texto: {razao:.2f}:1")

    def test_as_tres_severidades_tem_cores_diferentes_entre_si(self) -> None:
        """Sem isto, "distinguir erro de informação sem ler o texto" seria promessa vazia."""
        cores = {tokens.RESERVA[rodape.PAPEL_DE_TEXTO[s]] for s in rodape.SEVERIDADES}
        self.assertEqual(len(cores), len(rodape.SEVERIDADES))


class OrigemTests(unittest.TestCase):
    def test_a_mensagem_diz_de_qual_painel_ela_e(self) -> None:
        """O defeito: "Dataset carregado: 3936 amostras." na tela durante o trabalho na Galeria."""
        self.assertEqual(rodape.com_origem("3.936 amostras", "Dataset"), "Dataset: 3.936 amostras")

    def test_sem_origem_a_frase_fica_como_veio(self) -> None:
        self.assertEqual(rodape.com_origem("Pronto."), "Pronto.")
        self.assertEqual(rodape.com_origem("", "Dataset"), "", "prefixo sozinho não é mensagem")


class DocumentoTests(unittest.TestCase):
    def test_a_pagina_concluida_e_uma_frase_e_nao_uma_parcela_na_soma(self) -> None:
        """A pergunta é "posso virar?", e contar retângulo verde é a resposta pela metade (S-142)."""
        texto = rodape.descricao_dos_diagramas(3, salvos=3, todos_salvos=True)
        self.assertIn("página concluída", texto)
        self.assertNotIn("de 3 salvo", texto)

    def test_a_fracao_diz_quanto_falta_e_o_numero_solto_nao(self) -> None:
        texto = rodape.descricao_dos_diagramas(5, lidos=1, salvos=2)
        self.assertIn("5 diagrama(s)", texto)
        self.assertIn("1 lido(s)", texto)
        self.assertIn("2 de 5 salvo(s)", texto)

    def test_pagina_sem_diagrama_diz_isso_em_vez_de_ficar_muda(self) -> None:
        self.assertIn("nenhum diagrama", rodape.descricao_dos_diagramas(0))

    def test_a_pagina_concluida_fala_em_verde_e_o_resto_no_cinza_de_apoio(self) -> None:
        self.assertEqual(rodape.papel_do_documento(True), tokens.PRONTO_TEXTO)
        self.assertEqual(rodape.papel_do_documento(False), tokens.TEXTO_SECUNDARIO)

    def test_o_documento_nomeia_livro_e_pagina_em_base_1(self) -> None:
        texto = rodape.descricao_do_documento("Karpov A", 11, 402, "5 diagrama(s)")
        self.assertIn("Karpov A", texto)
        self.assertIn("p. 12 de 402", texto)
        self.assertIn("5 diagrama(s)", texto)

    def test_sem_livro_a_zona_fica_vazia_em_vez_de_dizer_p_1_de_0(self) -> None:
        self.assertEqual(rodape.descricao_do_documento(""), "")

    def test_pagina_fora_da_faixa_e_omitida_como_no_titulo_da_janela(self) -> None:
        """Mesma regra da S-167: um "p. 500 de 402" erra na única coisa que ele existe para dizer."""
        self.assertEqual(rodape.descricao_do_documento("Livro", 500, 402), "Livro")


class DispositivosTests(unittest.TestCase):
    """A zona 4: dois modelos torch no mesmo processo, e qual dispositivo cada um usa (S-182).

    O defeito que ela evita é o da S-30 repetido em dobro: uma máquina com placa mas com o torch
    `+cpu` roda na CPU em silêncio, e agora há **dois** modelos que podem cair nisso de forma
    independente.
    """

    def test_a_zona_diz_os_dois_modelos_e_nao_so_o_de_caracteres(self) -> None:
        curto, _ = rodape.descricao_dos_dispositivos("cuda:0 (NVIDIA GeForce RTX 4060)", "cpu (torch 2.4.1)")
        self.assertIn("peças cuda:0", curto)
        self.assertIn("texto cpu", curto)

    def test_o_nome_da_placa_sai_da_zona_e_fica_na_dica(self) -> None:
        """A zona disputa largura com a mensagem; a placa tem 24 caracteres e não decide nada."""
        curto, dica = rodape.descricao_dos_dispositivos("cuda:0 (NVIDIA GeForce RTX 4060)", "cuda:0 (NVIDIA GeForce RTX 4060)")
        self.assertNotIn("NVIDIA", curto)
        self.assertIn("NVIDIA GeForce RTX 4060", dica)

    def test_o_modelo_de_pecas_nao_carregado_nao_e_dito_como_cpu(self) -> None:
        """Supor o dispositivo antes da primeira leitura é o erro que a S-30 nomeia."""
        curto, _ = rodape.descricao_dos_dispositivos(None, "cpu (torch 2.4.1)")
        self.assertIn(rodape.SEM_MODELO, curto)
        self.assertNotIn("peças cpu", curto)

    def test_sem_pesos_a_dica_diz_onde_apontar_o_arquivo(self) -> None:
        """O clone limpo cai aqui por construção: o metadado é versionado e o `.pt` não."""
        curto, dica = rodape.descricao_dos_dispositivos(
            "cpu (torch 2.4.1)", None, motivo="Aponte o arquivo em data/settings.json."
        )
        self.assertIn(f"texto {rodape.SEM_PESOS}", curto)
        self.assertIn("data/settings.json", dica)

    def test_com_os_pesos_no_disco_e_outro_motor_a_zona_nao_manda_procurar_arquivo(self) -> None:
        """`rapidocr` escolhido não é `.pt` ausente, e a mesma palavra para os dois enganaria."""
        curto, dica = rodape.descricao_dos_dispositivos(
            "cpu (torch 2.4.1)", None, ausencia=rodape.DESLIGADO
        )
        self.assertIn(f"texto {rodape.DESLIGADO}", curto)
        self.assertNotIn(rodape.SEM_PESOS, curto)
        self.assertNotIn("data/settings.json", dica)


class OcupacaoTests(unittest.TestCase):
    """A projeção de `BusyRegistry.running()` para o que a barra mostra."""

    def test_sem_nada_rodando_a_barra_para_e_o_cancelar_desliga(self) -> None:
        atual = rodape.ocupacao([])
        self.assertEqual(atual.modo, rodape.PARADO)
        self.assertEqual(atual.texto, "")
        self.assertFalse(atual.cancelavel)

    def test_uma_operacao_fala_o_nome_e_o_detalhe_que_ela_mantem(self) -> None:
        registro = BusyRegistry()
        registro.register("treino do modelo", loses_work=True, detail="época 3 de 8")

        atual = rodape.ocupacao(registro.running())

        self.assertEqual(atual.modo, rodape.INDETERMINADO)
        self.assertIn("treino do modelo", atual.texto)
        self.assertIn("época 3 de 8", atual.texto)

    def test_duas_operacoes_falam_a_contagem_porque_dois_nomes_nao_caberiam(self) -> None:
        registro = BusyRegistry()
        registro.register("exportação para PGN", loses_work=False)
        registro.register("treino do modelo", loses_work=True)

        self.assertIn("2 operações", rodape.ocupacao(registro.running()).texto)

    def test_com_total_conhecido_a_barra_fica_determinada_e_diz_quanto_falta(self) -> None:
        """As três operações longas do produto sabem o total; a barra passa a dizê-lo (S-164)."""
        registro = BusyRegistry()
        token = registro.register("exportação para PGN", loses_work=False, total=402)
        token.update("página 201 de 402", feito=201, total=402)

        atual = rodape.ocupacao(registro.running())

        self.assertEqual(atual.modo, rodape.DETERMINADO)
        self.assertAlmostEqual(atual.fracao, 0.5)

    def test_duas_operacoes_voltam_ao_indeterminado_em_vez_de_somar_fracoes(self) -> None:
        """120 de 402 páginas com 3 de 8 épocas somadas dariam o progresso de coisa nenhuma."""
        registro = BusyRegistry()
        registro.register("exportação para PGN", loses_work=False, total=402).update("p. 120", feito=120)
        registro.register("treino do modelo", loses_work=True, total=8).update("época 3", feito=3)

        atual = rodape.ocupacao(registro.running())

        self.assertEqual(atual.modo, rodape.INDETERMINADO)
        self.assertIsNone(atual.fracao)

    def test_o_cancelar_liga_quando_alguma_das_operacoes_sabe_parar(self) -> None:
        registro = BusyRegistry()
        registro.register("busca por posição", loses_work=True)
        registro.register("treino do modelo", loses_work=True, cancellable=True, cancel=lambda: None)

        self.assertTrue(rodape.ocupacao(registro.running()).cancelavel)


class ComposicaoTests(unittest.TestCase):
    def test_uma_mensagem_de_um_painel_nao_apaga_o_livro_e_a_pagina(self) -> None:
        """O defeito 2 dito por inteiro: as três zonas são independentes."""
        estado = rodape.compor(
            mensagem="3.936 amostras carregadas", origem="Dataset", documento="Karpov A · p. 12 de 402"
        )
        self.assertIn("Dataset", estado.mensagem)
        self.assertEqual(estado.documento, "Karpov A · p. 12 de 402")

    def test_a_severidade_declarada_ganha_da_inferida(self) -> None:
        """Quem chama sabe mais que a lista de marcas -- ela é o piso, não o teto."""
        estado = rodape.compor(mensagem="Nada de anormal aqui", severidade=rodape.ERRO)
        self.assertEqual(estado.severidade, rodape.ERRO)


class WidgetTests(unittest.TestCase):
    """O rodapé montado: altura constante, e o que cada zona mostra."""

    root: tk.Tk

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = raiz()

    def setUp(self) -> None:
        self.janela = tk.Toplevel(self.root)
        self.janela.geometry("1200x200")
        self.addCleanup(self.janela.destroy)
        self.cancelados = 0
        self.painel = rodape.RodapeDaJanela(self.janela, cancelar=self._cancelar)
        self.painel.pack(side=tk.BOTTOM, fill=tk.X)
        self.janela.update()

    def _cancelar(self) -> None:
        self.cancelados += 1

    def test_a_altura_nao_muda_com_o_conteudo(self) -> None:
        """A consequência 4, medida: o comprimento do texto movia o layout acima dele.

        Todo widget do rodapé existe sempre; o que muda é texto, cor e estado. É isso que faz a
        altura ser fixa sem um número de pixel cravado em lugar nenhum.
        """
        vazio = self.painel.winfo_reqheight()

        self.painel.mostrar(
            "Página 12 anotada no conjunto de campo: 5 diagrama(s), 2 conferido(s). "
            "O conjunto tem 38 página(s) revisada(s)."
        )
        self.painel.definir_documento("Yusupov A — Boost your Chess 1 · p. 212 de 402 · 5 de 7 salvo(s)")
        registro = BusyRegistry()
        registro.register("exportação para PGN", loses_work=False, detail="página 120 de 402")
        self.painel.aplicar_ocupacao(registro.running())
        self.janela.update()

        self.assertEqual(self.painel.winfo_reqheight(), vazio)

    def test_a_zona_de_dispositivos_nao_muda_a_altura_do_rodape(self) -> None:
        """A quarta zona entrou depois da S-163, e a regra dela é a mesma: nada aparece nem some."""
        vazio = self.painel.winfo_reqheight()

        self.painel.definir_dispositivos(
            rodape.Dispositivos(pecas="cuda:0 (NVIDIA GeForce RTX 4060)", caracteres="cpu (torch 2.4.1)")
        )
        self.janela.update()

        self.assertEqual(self.painel.winfo_reqheight(), vazio)
        self.assertIn("texto cpu", self.painel.dispositivos())

    def test_o_rodape_pergunta_os_dispositivos_no_mesmo_tique_da_ocupacao(self) -> None:
        """Um segundo temporizador seria outra coisa para esquecer de cancelar (S-112)."""
        perguntas = []

        def responder() -> rodape.Dispositivos:
            perguntas.append(1)
            return rodape.Dispositivos(pecas="cpu (torch 2.4.1)", caracteres="cpu (torch 2.4.1)")

        self.painel.acompanhar(lambda: [], dispositivos=responder, intervalo_ms=10_000)
        self.janela.update()

        self.assertEqual(len(perguntas), 1)
        self.assertEqual(self.painel.dispositivos(), "peças cpu · texto cpu")

    def test_o_erro_se_distingue_da_informacao_sem_ler_o_texto(self) -> None:
        self.painel.mostrar("Exemplo salvo.")
        informacao = str(self.painel._lbl_mensagem.cget("foreground"))
        self.painel.mostrar("Falha no OCR.")
        erro = str(self.painel._lbl_mensagem.cget("foreground"))

        self.assertNotEqual(informacao, erro)

    def test_a_mensagem_de_erro_nao_tem_prazo_agendado(self) -> None:
        """A expiração é do relógio do Tk; o que se afirma aqui é que erro não agenda nenhuma."""
        self.painel.mostrar("Falha no OCR.")
        self.assertIsNone(self.painel._expiracao)
        self.painel.mostrar("Modelo recarregado.")
        self.assertIsNotNone(self.painel._expiracao)

    def test_o_botao_de_cancelar_chama_quem_sabe_parar(self) -> None:
        registro = BusyRegistry()
        registro.register("treino do modelo", loses_work=True, cancellable=True, cancel=lambda: None)
        self.painel.aplicar_ocupacao(registro.running())

        self.assertEqual(str(self.painel._btn_cancelar.cget("state")), tk.NORMAL)
        self.painel._btn_cancelar.invoke()
        self.assertEqual(self.cancelados, 1)

    def test_sem_operacao_o_cancelar_fica_desabilitado(self) -> None:
        self.painel.aplicar_ocupacao([])
        self.assertEqual(str(self.painel._btn_cancelar.cget("state")), tk.DISABLED)

    def test_a_barra_determinada_anda_e_a_indeterminada_nao_reinicia(self) -> None:
        """O valor é escrito a cada tique; o modo, só quando muda -- senão a animação travaria.

        `start()` chamado quatro vezes por segundo reinicia a animação da barra indeterminada, e
        o efeito na tela é uma barra que parece parada justamente durante a operação longa.
        """
        registro = BusyRegistry()
        token = registro.register("varredura da fila de revisão", loses_work=False, total=100)
        token.update("página 40 de 100", feito=40)
        self.painel.aplicar_ocupacao(registro.running())
        self.assertAlmostEqual(float(self.painel._barra.cget("value")), 40.0)

        token.update("página 80 de 100", feito=80)
        self.painel.aplicar_ocupacao(registro.running())
        self.assertAlmostEqual(float(self.painel._barra.cget("value")), 80.0)
        self.assertEqual(str(self.painel._barra.cget("mode")), "determinate")

    def test_a_barra_volta_a_zero_quando_a_operacao_termina(self) -> None:
        registro = BusyRegistry()
        token = registro.register("exportação para PGN", loses_work=False, total=10)
        token.update("página 9 de 10", feito=9)
        self.painel.aplicar_ocupacao(registro.running())
        token.release()

        self.painel.aplicar_ocupacao(registro.running())

        self.assertAlmostEqual(float(self.painel._barra.cget("value")), 0.0)
        self.assertEqual(self.painel._modo_da_barra, rodape.PARADO)

    def test_o_rodape_e_visivel_no_piso_da_janela(self) -> None:
        """O critério de aceite: visível em qualquer tamanho que o piso da S-150 permita."""
        self.janela.geometry("1180x800")
        self.janela.update()
        self.assertTrue(self.painel.winfo_ismapped())
        self.assertGreater(self.painel.winfo_height(), 1)


if __name__ == "__main__":
    unittest.main()
