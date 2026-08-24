"""A sessão de transcrição das faixas de referência, sem janela (S-183).

O que se testa aqui é o que erra em silêncio numa sessão de 123 faixas: o `\\n` que o `Text`
do Tk acrescenta, a semente sobrescrita por engano, a volta que o "próxima pendente" tem de
dar, e a gravação por cima de um arquivo que outra sessão mexeu.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from chess_diagram_ocr.text.transcricao import (
    ReferenciaMudouNoDisco,
    SessaoDeTranscricao,
    normalizar_texto,
)


def _linha(**campos: object) -> dict[str, object]:
    base: dict[str, object] = {
        "pdf": "Livro.pdf",
        "pagina": 12,
        "bbox_pt": [10.0, 20.0, 30.0, 40.0],
        "texto": "",
        "lado": None,
        "numero": None,
        "jogadores": None,
        "evento": None,
        "ano": None,
        "conferido": False,
        "semeado_de": None,
        "texto_semente": "",
    }
    base.update(campos)
    return base


def _gravar(pasta: Path, *linhas: dict[str, object]) -> Path:
    caminho = pasta / "referencia.jsonl"
    corpo = "\n".join(json.dumps(linha, ensure_ascii=False) for linha in linhas) + "\n"
    caminho.write_bytes(corpo.encode("utf-8"))
    return caminho


class NormalizacaoTests(unittest.TestCase):
    def test_o_enter_final_do_Text_nao_vira_caractere_da_referencia(self) -> None:
        """O `Text` do Tk sempre devolve `\\n` no fim, e a `cer` contaria esse caractere."""
        self.assertEqual(normalizar_texto("Hickl - Yusupov\n"), "Hickl - Yusupov")

    def test_linhas_de_dentro_sobrevivem(self) -> None:
        self.assertEqual(normalizar_texto("Hickl - Yusupov\nBremen 1998\n"), "Hickl - Yusupov\nBremen 1998")

    def test_espaco_a_direita_e_linha_em_branco_nas_pontas_saem(self) -> None:
        self.assertEqual(normalizar_texto("\n\n  Mat em 2   \n\n"), "Mat em 2")

    def test_crlf_vira_lf(self) -> None:
        self.assertEqual(normalizar_texto("a\r\nb"), "a\nb")


class SessaoTests(unittest.TestCase):
    def test_carregar_casa_o_png_pelo_numero_do_prefixo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            caminho = _gravar(pasta, _linha(), _linha(pagina=13), _linha(pagina=14))
            pngs = pasta / "pngs"
            pngs.mkdir()
            (pngs / "001_p12.png").write_bytes(b"x")
            (pngs / "003_p14.png").write_bytes(b"x")
            (pngs / "leiame.txt").write_text("não é faixa", encoding="utf-8")

            sessao = SessaoDeTranscricao.carregar(caminho, pngs)

            self.assertEqual(sessao.total, 3)
            self.assertEqual(sessao.itens[0].imagem, pngs / "001_p12.png")
            self.assertIsNone(sessao.itens[1].imagem, "a faixa 2 não tem PNG, e isso é caminho normal")
            self.assertEqual(sessao.itens[2].imagem, pngs / "003_p14.png")

    def test_gravar_sem_editar_devolve_o_arquivo_byte_a_byte(self) -> None:
        """A sessão que só navegou não pode reescrever o arquivo de outro jeito."""
        with tempfile.TemporaryDirectory() as tmp:
            caminho = _gravar(
                Path(tmp),
                _linha(texto="Mat em 2", conferido=True, semeado_de="camada", texto_semente="Mat em 2"),
                _linha(pagina=13, jogadores=["Hickl", "Yusupov"], ano=1998),
            )
            antes = caminho.read_bytes()

            sessao = SessaoDeTranscricao.carregar(caminho)
            sessao.proximo()
            sessao.salvar()

            self.assertEqual(caminho.read_bytes(), antes)

    def test_editar_nao_toca_na_semente(self) -> None:
        """A semente é o registro do que a máquina escreveu -- é contra ela que a tabela conta
        as células circulares."""
        with tempfile.TemporaryDirectory() as tmp:
            caminho = _gravar(
                Path(tmp), _linha(texto="Mat em 2", semeado_de="camada", texto_semente="Mat em 2")
            )
            sessao = SessaoDeTranscricao.carregar(caminho)

            self.assertTrue(sessao.editar(texto="Mate in 2\n", conferido=True))

            faixa = sessao.atual.faixa
            self.assertEqual(faixa.texto, "Mate in 2")
            self.assertEqual(faixa.texto_semente, "Mat em 2")
            self.assertEqual(faixa.semeado_de, "camada")
            self.assertFalse(sessao.atual.circular, "mudou uma letra: deixou de ser circular")
            self.assertTrue(sessao.sujo)

    def test_editar_com_o_mesmo_valor_nao_suja_a_sessao(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            caminho = _gravar(Path(tmp), _linha(texto="Mat em 2"))
            sessao = SessaoDeTranscricao.carregar(caminho)

            self.assertFalse(sessao.editar(texto="Mat em 2\n", conferido=False))
            self.assertFalse(sessao.sujo)

    def test_restaurar_semente_sem_semente_nao_faz_nada(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            caminho = _gravar(Path(tmp), _linha(texto="digitado à mão"))
            sessao = SessaoDeTranscricao.carregar(caminho)

            self.assertFalse(sessao.restaurar_semente())
            self.assertEqual(sessao.atual.faixa.texto, "digitado à mão")

    def test_restaurar_semente_devolve_o_que_a_camada_escreveu(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            caminho = _gravar(
                Path(tmp), _linha(texto="corrigido", semeado_de="camada", texto_semente="Mat em 2")
            )
            sessao = SessaoDeTranscricao.carregar(caminho)

            self.assertTrue(sessao.restaurar_semente())
            self.assertEqual(sessao.atual.faixa.texto, "Mat em 2")

    def test_proxima_pendente_da_a_volta(self) -> None:
        """Quem começou pelo meio ainda tem pendentes atrás, e parar no fim esconderia metade."""
        with tempfile.TemporaryDirectory() as tmp:
            caminho = _gravar(
                Path(tmp),
                _linha(conferido=False),
                _linha(pagina=13, conferido=True),
                _linha(pagina=14, conferido=True),
            )
            sessao = SessaoDeTranscricao.carregar(caminho)
            sessao.ir_para(2)

            self.assertTrue(sessao.proxima_pendente())
            self.assertEqual(sessao.indice, 0)

    def test_proxima_pendente_sem_pendente_devolve_falso(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            caminho = _gravar(Path(tmp), _linha(conferido=True), _linha(pagina=13, conferido=True))
            sessao = SessaoDeTranscricao.carregar(caminho)

            self.assertFalse(sessao.proxima_pendente())

    def test_navegar_nao_sai_da_lista(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            caminho = _gravar(Path(tmp), _linha(), _linha(pagina=13))
            sessao = SessaoDeTranscricao.carregar(caminho)

            self.assertFalse(sessao.anterior())
            self.assertTrue(sessao.proximo())
            self.assertFalse(sessao.proximo())
            self.assertEqual(sessao.indice, 1)


class GravacaoConcorrenteTests(unittest.TestCase):
    def test_gravar_recusa_quando_o_arquivo_mudou_no_disco(self) -> None:
        """Mais de uma sessão escreve nesta árvore, e aqui a sobrescrita apaga trabalho humano
        em vez de um artefato reconstruível."""
        with tempfile.TemporaryDirectory() as tmp:
            caminho = _gravar(Path(tmp), _linha())
            sessao = SessaoDeTranscricao.carregar(caminho)
            sessao.editar(texto="o que eu digitei", conferido=True)

            _gravar(Path(tmp), _linha(texto="o que a outra sessão conferiu", conferido=True))

            with self.assertRaises(ReferenciaMudouNoDisco):
                sessao.salvar()
            self.assertIn("outra sessão", caminho.read_text(encoding="utf-8"))
            self.assertTrue(sessao.sujo, "recusar não pode limpar a marca de trabalho por gravar")

    def test_gravar_duas_vezes_seguidas_funciona(self) -> None:
        """A guarda acima não pode confundir a própria gravação com a de outro."""
        with tempfile.TemporaryDirectory() as tmp:
            caminho = _gravar(Path(tmp), _linha())
            sessao = SessaoDeTranscricao.carregar(caminho)

            sessao.editar(texto="primeiro", conferido=True)
            sessao.salvar()
            sessao.editar(texto="segundo")
            sessao.salvar()

            gravado = json.loads(caminho.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(gravado["texto"], "segundo")
            self.assertFalse(sessao.sujo)


class AvisosTests(unittest.TestCase):
    def test_conferida_e_vazia_e_avisada_e_nao_impedida(self) -> None:
        """`cer()` devolve infinito com referência vazia: não é zero silencioso, mas também
        não costuma ser o que alguém quis dizer."""
        with tempfile.TemporaryDirectory() as tmp:
            caminho = _gravar(Path(tmp), _linha(texto="", conferido=True))
            sessao = SessaoDeTranscricao.carregar(caminho)

            avisos = sessao.avisos()

            self.assertEqual(len(avisos), 1)
            self.assertIn("vazio", avisos[0])
            sessao.salvar()  # não impede

    def test_a_semente_intocada_e_contada_como_circular(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            caminho = _gravar(
                Path(tmp),
                _linha(texto="Mat em 2", conferido=True, semeado_de="camada", texto_semente="Mat em 2"),
                _linha(pagina=13, texto="corrigido", conferido=True, semeado_de="camada", texto_semente="Mat em 3"),
            )
            sessao = SessaoDeTranscricao.carregar(caminho)

            self.assertEqual(sessao.circulares, 1)
            self.assertIn("circular", " ".join(sessao.avisos()))

    def test_sessao_limpa_nao_tem_aviso(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            caminho = _gravar(Path(tmp), _linha(texto="Mat em 2", conferido=True))
            sessao = SessaoDeTranscricao.carregar(caminho)

            self.assertEqual(sessao.avisos(), [])
            self.assertEqual(sessao.conferidas, 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
