"""As últimas mensagens do rodapé, sem toolkit (OCR_UI C2, A10; análise §6.8).

Informação expira em 20 s e aviso em 40 s, e o que expirava sumia. `Mensagens` é o anel das
últimas cinquenta, puro; `qt/rodape.py` o alimenta a cada `mostrar` e o desenha atrás do botão
«Mensagens». A severidade continua vindo de `severidade_de` quando o emissor não a declara.
"""

from __future__ import annotations

import unittest

from chess_diagram_ocr.ui.estado_do_rodape import (
    AVISO,
    ERRO,
    INFORMACAO,
    TETO_DE_MENSAGENS,
    Mensagens,
    severidade_de,
)


class MensagensTests(unittest.TestCase):
    def test_guarda_na_ordem_e_com_a_severidade(self) -> None:
        anel = Mensagens()
        anel.registrar("Abra um livro", AVISO, quando="10:00:00")
        anel.registrar("Amostra gravada", INFORMACAO, quando="10:00:05")
        self.assertEqual([m.texto for m in anel.todas()], ["Abra um livro", "Amostra gravada"])
        self.assertEqual([m.severidade for m in anel.todas()], [AVISO, INFORMACAO])

    def test_a_vazia_nao_entra(self) -> None:
        """O rodapé limpo não é mensagem: registrá-lo encheria a lista de linhas em branco."""
        anel = Mensagens()
        self.assertIsNone(anel.registrar("   ", INFORMACAO, quando="10:00:00"))
        self.assertEqual(len(anel), 0)

    def test_o_teto_e_cinquenta_e_descarta_a_mais_antiga(self) -> None:
        self.assertEqual(TETO_DE_MENSAGENS, 50)
        anel = Mensagens()
        for i in range(60):
            anel.registrar(f"m{i}", INFORMACAO, quando="10:00:00")
        self.assertEqual(len(anel), 50)
        self.assertEqual(anel.todas()[0].texto, "m10")
        self.assertEqual(anel.todas()[-1].texto, "m59")

    def test_a_linha_diz_a_hora_e_a_severidade_quando_nao_e_informacao(self) -> None:
        anel = Mensagens()
        info = anel.registrar("Amostra gravada", INFORMACAO, quando="10:00:05")
        erro = anel.registrar("Falha ao salvar", ERRO, quando="10:00:09")
        assert info is not None and erro is not None
        self.assertEqual(info.linha(), "10:00:05  Amostra gravada")
        self.assertEqual(erro.linha(), "10:00:09 [erro]  Falha ao salvar")


class SeveridadeDeclaradaTests(unittest.TestCase):
    """A heurística continua sendo a rede; o que muda em A10 são os emissores."""

    def test_a_heuristica_pintaria_de_informacao_o_que_e_aviso(self) -> None:
        """É a frase que `janela._rodar` passou a declarar como aviso: «já há uma tarefa em
        andamento» pede outra ação da pessoa, e a heurística, sem marca nenhuma, a deixaria cinza."""
        self.assertEqual(severidade_de("Já há uma tarefa em andamento."), INFORMACAO)

    def test_a_heuristica_continua_pegando_a_falha_sem_declaracao(self) -> None:
        self.assertEqual(severidade_de("Falha ao gravar a amostra."), ERRO)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
