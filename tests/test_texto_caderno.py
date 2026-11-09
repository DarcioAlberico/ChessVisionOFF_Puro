"""O caderno do livro, puro: uma folha por arquivo, sem poda, achado pelo conteúdo (S-610).

Os critérios de aceite da S-610 em `docs/ROADMAP_MESA_DE_TEXTO.md`, cada um num teste: 300 folhas
deixam 300 arquivos, a gravação interrompida deixa a versão anterior legível, o livro movido e o
livro duplicado abrem um caderno só, e a trava de um processo vivo deixa o segundo só para leitura.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from ambiente_de_teste import pasta_temporaria
from subprocesso import iniciar_python

from chess_diagram_ocr.arquivo_do_dono import GravacaoRecusada
from chess_diagram_ocr.text import arquivo, caderno, rico
from chess_diagram_ocr.text.pagina import BlocoDeTexto, Coluna, LinhaLida, PaginaLida


def _pagina(livro: str, folha: int = 0, texto: str = "uma folha lida") -> PaginaLida:
    bloco = BlocoDeTexto.de_linhas([LinhaLida(texto, (0.0, 0.0, 100.0, 9.0), 0.5, "glifo")])  # type: ignore[arg-type]
    return PaginaLida(documento=livro, pagina=folha, colunas=(Coluna(indice=0, blocos=(bloco,)),))


def _doc(livro: Path, folha: int = 0, texto: str = "uma folha lida") -> rico.DocumentoRico:
    return rico.de_pagina(_pagina(str(livro), folha, texto))


def _editado(doc: rico.DocumentoRico, acrescimo: str) -> rico.DocumentoRico:
    fim = len(doc.para_texto())
    return rico.editar(doc, fim, fim, acrescimo)


class _ComLivro(unittest.TestCase):
    def setUp(self) -> None:
        self.raiz = pasta_temporaria(self)
        self.pasta = self.raiz / "cadernos"
        self.livro = self.raiz / "livros" / "Nunn - Understanding.pdf"
        self.livro.parent.mkdir(parents=True)
        self.livro.write_bytes(b"%PDF-1.7\n" + bytes(range(256)) * 64)

    def abrir(self, livro: Path | None = None) -> caderno.Caderno:
        aberto = caderno.abrir(livro or self.livro, pasta=self.pasta)
        assert aberto is not None
        self.addCleanup(aberto.fechar)
        return aberto


class GravarTests(_ComLivro):
    def test_trezentas_folhas_deixam_trezentos_arquivos_e_um_indice(self) -> None:
        livro = self.abrir()
        for folha in range(300):
            self.assertEqual(livro.gravar(_doc(self.livro, folha, f"folha {folha}")), caderno.GRAVADA)
        arquivos = sorted(livro.pasta.glob(f"folha-[0-9][0-9][0-9][0-9]{arquivo.EXTENSAO}"))
        self.assertEqual(len(arquivos), 300, "o caderno podou")
        self.assertEqual(len(caderno.abrir(self.livro, pasta=self.pasta).folhas()), 300)  # type: ignore[union-attr]

    def test_a_folha_volta_igual(self) -> None:
        livro = self.abrir()
        doc = _editado(_doc(self.livro, 4), " corrigida")
        livro.gravar(doc, correcoes=1)
        self.assertEqual(self.abrir().folha(4), doc)
        self.assertEqual(livro.estado(4).estado, caderno.EDITADA)  # type: ignore[union-attr]
        self.assertEqual(livro.estado(4).correcoes, 1)  # type: ignore[union-attr]

    def test_gravar_o_mesmo_nao_reescreve(self) -> None:
        livro = self.abrir()
        doc = _doc(self.livro)
        livro.gravar(doc)
        self.assertFalse(livro.difere(doc))
        self.assertEqual(livro.gravar(doc), caderno.IGUAL)
        self.assertTrue(livro.difere(_editado(doc, "!")))

    def test_gravacao_interrompida_deixa_a_versao_anterior_legivel(self) -> None:
        livro = self.abrir()
        livro.gravar(_doc(self.livro, 0, "a versão boa"))
        with mock.patch.object(caderno.os, "replace", side_effect=OSError("disco cheio")):
            with self.assertRaises(OSError):
                livro.gravar(_doc(self.livro, 0, "a versão nova"))
        self.assertIn("a versão boa", arquivo.carregar(livro.caminho(0)).para_texto())
        self.assertEqual(list(livro.pasta.glob(".*.tmp")), [], "o temporário ficou para trás")

    def test_a_folha_vazia_nao_vai_por_cima_da_que_tem_texto(self) -> None:
        livro = self.abrir()
        doc = _doc(self.livro, 2, "texto que custou")
        livro.gravar(doc)
        vazia = rico.editar(doc, 0, len(doc.para_texto()), "")
        self.assertEqual(livro.gravar(vazia), caderno.RECUSADA_VAZIA)
        self.assertIn("texto que custou", livro.folha(2).para_texto())  # type: ignore[union-attr]

    def test_documento_sem_folha_nao_tem_caderno(self) -> None:
        self.assertEqual(self.abrir().gravar(rico.DocumentoRico()), caderno.SEM_FOLHA)


class AnteriorTests(_ComLivro):
    def test_a_primeira_gravacao_da_visita_guarda_a_folha_de_antes(self) -> None:
        livro = self.abrir()
        livro.gravar(_doc(self.livro, 0, "como estava"))
        livro.visitar(0)
        livro.gravar(_doc(self.livro, 0, "primeira mudança"))
        livro.gravar(_doc(self.livro, 0, "segunda mudança"))
        self.assertIn("como estava", livro.anterior(0).para_texto())  # type: ignore[union-attr]
        self.assertIn("segunda", livro.folha(0).para_texto())  # type: ignore[union-attr]

    def test_ler_de_novo_guarda_a_corrigida_como_anterior_e_a_leitura_como_lida(self) -> None:
        livro = self.abrir()
        livro.guardar_leitura(_doc(self.livro, 0, "lida pelo glifo"), motor="glifo", modo_bloco=False)
        livro.gravar(_doc(self.livro, 0, "corrigida à mão"), correcoes=3)
        livro.guardar_leitura(_doc(self.livro, 0, "lida pelo auto"), motor="auto", modo_bloco=True)
        self.assertIn("corrigida", livro.anterior(0).para_texto())  # type: ignore[union-attr]
        self.assertIn("auto", livro.lida(0).para_texto())  # type: ignore[union-attr]
        estado = livro.estado(0)
        assert estado is not None
        self.assertEqual((estado.estado, estado.motor, estado.modo_bloco, estado.correcoes), (caderno.LIDA, "auto", True, 0))


class FolhaIlegivelTests(_ComLivro):
    """S-896: a folha que não abre -- versão futura, ou corrompida -- não é gravada por cima."""

    ESTRAGOS = {
        "versão futura": json.dumps({"versao": 99, "documento": {"corridas": []}}).encode("utf-8"),
        "corrompida": b'{"versao": 1, "documento": {"corr',
    }

    def _corrigida_e_estragada(self, bytes_ruins: bytes) -> caderno.Caderno:
        """Uma folha `editada` com 12 correções, cujo arquivo depois deixa de abrir; o caderno reaberto."""
        livro = self.abrir()
        livro.gravar(_doc(self.livro, 2, "corrigida à mão"), correcoes=12)
        livro.fechar()
        livro.caminho(2).write_bytes(bytes_ruins)
        return self.abrir()

    def test_nenhum_gravador_escreve_por_cima_e_o_indice_fica(self) -> None:
        for nome, ruins in self.ESTRAGOS.items():
            with self.subTest(nome):
                shutil.rmtree(self.pasta, ignore_errors=True)
                livro = self._corrigida_e_estragada(ruins)
                self.assertIsNone(livro.folha(2))
                self.assertIsNotNone(livro.trava(2))
                self.assertEqual(livro.guardar_leitura(_doc(self.livro, 2, "lida de novo"), motor="glifo", modo_bloco=False), caderno.TRAVADA)
                self.assertEqual(livro.gravar(_doc(self.livro, 2, "outra coisa"), correcoes=1), caderno.TRAVADA)
                with self.assertRaises(GravacaoRecusada):
                    livro.trazer_rascunho(_doc(self.livro, 2, "do rascunho"), datetime.now(timezone.utc))
                self.assertEqual(livro.caminho(2).read_bytes(), ruins)
                self.assertFalse(livro.caminho(2, tipo="lida").exists())
                estado = livro.estado(2)
                assert estado is not None
                self.assertEqual((estado.estado, estado.correcoes), (caderno.EDITADA, 12))
                self.assertEqual([f.pagina for f in livro.corrigidas()], [2])
                (copia,) = livro.pasta.glob("folha-0003.ilegivel-*.cvtxt")
                self.assertEqual(copia.read_bytes(), ruins)
                livro.fechar()

    def test_apagada_a_folha_ruim_o_caderno_grava_de_novo(self) -> None:
        livro = self._corrigida_e_estragada(self.ESTRAGOS["corrompida"])
        self.assertIsNotNone(livro.trava(2))
        livro.caminho(2).unlink()
        self.assertIsNone(livro.trava(2))
        self.assertEqual(livro.gravar(_doc(self.livro, 2, "refeita"), correcoes=1), caderno.GRAVADA)


class IdentidadeTests(_ComLivro):
    def test_mover_o_pdf_abre_o_caderno_de_antes(self) -> None:
        livro = self.abrir()
        livro.gravar(_doc(self.livro, 0, "corrigida antes da mudança"))
        livro.fechar()
        movido = self.raiz / "outra pasta" / "renomeado.pdf"
        movido.parent.mkdir()
        shutil.move(self.livro, movido)
        reaberto = self.abrir(movido)
        self.assertIn("corrigida", reaberto.folha(0).para_texto())  # type: ignore[union-attr]
        self.assertEqual(reaberto.apelidos, (str(self.livro), str(movido)))

    def test_o_mesmo_livro_em_duas_pastas_abre_um_caderno(self) -> None:
        copia = self.raiz / "copia" / self.livro.name
        copia.parent.mkdir()
        shutil.copy(self.livro, copia)
        um = self.abrir()
        um.fechar()
        self.assertEqual(self.abrir(copia).pasta, um.pasta)
        self.assertEqual(len(list(self.pasta.iterdir())), 1)

    def test_livros_diferentes_tem_cadernos_diferentes(self) -> None:
        outro = self.raiz / "livros" / "outro.pdf"
        outro.write_bytes(b"%PDF-1.7\n outro livro")
        self.assertNotEqual(self.abrir().pasta, self.abrir(outro).pasta)

    def test_pdf_pequeno_anotado_acha_o_mesmo_caderno(self) -> None:
        # Num PDF de menos de 1 MiB o primeiro MiB é o arquivo inteiro: a gravação incremental de uma
        # anotação muda a identidade, e o caderno ficava órfão (S-897). O caminho é o apelido.
        livro = self.abrir()
        livro.gravar(_doc(self.livro, 0, "corrigida antes da anotação"))
        livro.fechar()
        with open(self.livro, "ab") as fluxo:
            fluxo.write(b"\n1 0 obj << /Type /Annot >> endobj\n%%EOF\n")
        self.assertNotEqual(caderno.identidade_de(self.livro), livro.identidade)
        reaberto = self.abrir()
        self.assertEqual(reaberto.pasta, livro.pasta)
        self.assertIn("corrigida", reaberto.folha(0).para_texto())  # type: ignore[union-attr]
        self.assertEqual(len(list(self.pasta.iterdir())), 1)

    def test_apelido_gravado_em_outra_caixa_e_barra_ainda_acha(self) -> None:
        # O índice do dono guarda `str(Path(pdf))` como veio; o mesmo livro é a regra de `ui.livros`.
        livro = self.abrir()
        livro.fechar()
        indice = livro.pasta / "indice.json"
        dados = json.loads(indice.read_text(encoding="utf-8"))
        dados["apelidos"] = [str(self.livro.parent / ".." / "livros" / self.livro.name)]
        indice.write_bytes(json.dumps(dados).encode("utf-8"))
        with open(self.livro, "ab") as fluxo:
            fluxo.write(b"%%EOF\n")
        self.assertEqual(self.abrir().pasta, livro.pasta)

    def test_livro_que_nao_abre_nao_tem_caderno(self) -> None:
        self.assertIsNone(caderno.abrir(self.raiz / "nao existe.pdf", pasta=self.pasta))


class IndiceTests(_ComLivro):
    def test_marcar_conferida_grava_o_indice(self) -> None:
        livro = self.abrir()
        livro.gravar(_doc(self.livro, 7))
        self.assertTrue(livro.marcar(7, caderno.CONFERIDA))
        livro.fechar()
        self.assertEqual(self.abrir().conferidas(), 1)

    def test_indice_corrompido_e_refeito_pelas_folhas(self) -> None:
        livro = self.abrir()
        livro.gravar(_doc(self.livro, 0))
        livro.gravar(_doc(self.livro, 5))
        livro.fechar()
        (livro.pasta / "indice.json").write_text("{ isto não é json", encoding="utf-8")
        self.assertEqual([f.pagina for f in self.abrir().folhas()], [0, 5])

    def test_rascunho_mais_novo_entra_e_o_mais_velho_nao(self) -> None:
        livro = self.abrir()
        self.assertTrue(livro.trazer_rascunho(_doc(self.livro, 4, "do rascunho"), datetime.now() - timedelta(days=1)))
        livro.gravar(_doc(self.livro, 6, "do caderno"))
        self.assertFalse(livro.trazer_rascunho(_doc(self.livro, 6, "rascunho velho"), datetime.now() - timedelta(days=2)))
        self.assertIn("do caderno", livro.folha(6).para_texto())  # type: ignore[union-attr]

    def _caderno_gravado_em(self, pagina: int, gravada_em: str) -> caderno.Caderno:
        """Um caderno com a folha `pagina` cuja hora no índice é `gravada_em` -- como o disco do dono a tem."""
        livro = self.abrir()
        livro.gravar(_doc(self.livro, pagina, "do caderno"))
        livro.fechar()
        indice = livro.pasta / "indice.json"
        dados = json.loads(indice.read_text(encoding="utf-8"))
        dados["folhas"][str(pagina + 1)]["gravada_em"] = gravada_em
        indice.write_bytes(json.dumps(dados).encode("utf-8"))
        return self.abrir()

    def test_rascunho_gravado_depois_da_volta_do_horario_entra_no_caderno(self) -> None:
        # 02:30 em +01:00 é 01:30 UTC; o rascunho das 02:10 em +00:00 é 02:10 UTC, 40 minutos depois.
        # Como texto, "02:30" > "02:10", e o rascunho mais novo era recusado (e o painel o apagava).
        livro = self._caderno_gravado_em(3, "2026-10-25T02:30:00+01:00")
        depois = datetime(2026, 10, 25, 2, 10, tzinfo=timezone(timedelta(hours=0)))
        self.assertTrue(livro.trazer_rascunho(_doc(self.livro, 3, "do rascunho"), depois))
        self.assertIn("do rascunho", livro.folha(3).para_texto())  # type: ignore[union-attr]

    def test_rascunho_mais_velho_em_outro_fuso_continua_recusado(self) -> None:
        # 02:30 em +00:00 é 02:30 UTC; 02:50 em +01:00 é 01:50 UTC: o texto diz mais novo, o instante não.
        livro = self._caderno_gravado_em(3, "2026-10-25T02:30:00+00:00")
        antes = datetime(2026, 10, 25, 2, 50, tzinfo=timezone(timedelta(hours=1)))
        self.assertFalse(livro.trazer_rascunho(_doc(self.livro, 3, "rascunho velho"), antes))
        self.assertIn("do caderno", livro.folha(3).para_texto())  # type: ignore[union-attr]

    def test_indice_antigo_sem_fuso_vale_como_hora_local(self) -> None:
        # Os índices gravados antes da S-908 não têm deslocamento: vale a hora local daquele momento.
        livro = self._caderno_gravado_em(3, "2026-10-24T14:02:11")
        self.assertFalse(livro.trazer_rascunho(_doc(self.livro, 3, "velho"), datetime(2026, 10, 24, 13, 0).astimezone()))
        self.assertTrue(livro.trazer_rascunho(_doc(self.livro, 3, "novo"), datetime(2026, 10, 24, 15, 0).astimezone()))
        self.assertIn("novo", livro.folha(3).para_texto())  # type: ignore[union-attr]

    def test_hora_ilegivel_no_indice_nao_recusa_o_rascunho(self) -> None:
        livro = self._caderno_gravado_em(3, "ontem à tarde")
        self.assertTrue(livro.trazer_rascunho(_doc(self.livro, 3, "do rascunho"), datetime(2026, 10, 24, 15, 0)))

    def test_gravar_anota_a_hora_com_fuso(self) -> None:
        livro = self.abrir()
        livro.gravar(_doc(self.livro, 2))
        gravada = datetime.fromisoformat(livro.estado(2).gravada_em)  # type: ignore[union-attr]
        self.assertIsNotNone(gravada.tzinfo, "a hora do índice saiu sem deslocamento")
        self.assertLess(abs(gravada - datetime.now(timezone.utc)), timedelta(minutes=1))


class TravaTests(_ComLivro):
    def test_trava_de_processo_vivo_abre_so_para_leitura(self) -> None:
        primeiro = self.abrir()
        primeiro.fechar()
        # O pai deste processo está vivo e não é este: é a outra janela.
        (primeiro.pasta / "caderno.lock").write_text(str(os.getppid()), encoding="utf-8")
        segundo = self.abrir()
        self.assertTrue(segundo.somente_leitura)
        self.assertIn("só para leitura", segundo.motivo)
        self.assertEqual(segundo.gravar(_doc(self.livro)), caderno.SOMENTE_LEITURA)
        self.assertFalse(segundo.caminho(0).exists())

    def test_trava_de_processo_morto_e_retomada(self) -> None:
        primeiro = self.abrir()
        primeiro.fechar()
        (primeiro.pasta / "caderno.lock").write_text("999999999", encoding="utf-8")
        segundo = self.abrir()
        self.assertFalse(segundo.somente_leitura)
        self.assertEqual(segundo.gravar(_doc(self.livro)), caderno.GRAVADA)

    def _trava_de_um_vivo(self, segunda_linha: str = "") -> tuple[Path, int]:
        """A trava em nome de um processo vivo que não é este; `segunda_linha` é a hora de criação."""
        vivo = iniciar_python("import time; time.sleep(60)")
        self.addCleanup(vivo.wait)
        self.addCleanup(vivo.kill)
        primeiro = self.abrir()
        primeiro.fechar()
        trava = primeiro.pasta / "caderno.lock"
        trava.write_bytes(f"{vivo.pid}\n{segunda_linha}".encode())
        return trava, vivo.pid

    def test_pid_vivo_com_hora_de_criacao_diferente_retoma_a_trava(self) -> None:
        # Depois de uma queda a trava fica, e o Windows reaproveita o PID logo: o processo vivo com
        # aquele número nasceu depois de quem gravou a trava, e é outro programa (S-897).
        self._trava_de_um_vivo("1000000000.0\n")
        segundo = self.abrir()
        self.assertFalse(segundo.somente_leitura, segundo.motivo)
        self.assertEqual(segundo.gravar(_doc(self.livro)), caderno.GRAVADA)

    @unittest.skipUnless(sys.platform == "win32" or Path("/proc/self/stat").exists(), "sem a hora de criação do processo")
    def test_pid_vivo_com_a_mesma_hora_de_criacao_segura_a_trava(self) -> None:
        trava, pid = self._trava_de_um_vivo()
        trava.write_bytes(f"{pid}\n{caderno._inicio_do_processo(pid)!r}\n".encode())
        self.assertTrue(self.abrir().somente_leitura)

    @unittest.skipUnless(sys.platform == "win32" or Path("/proc/self/stat").exists(), "sem a hora de criação do processo")
    def test_trava_antiga_mais_velha_que_o_processo_vivo_e_retomada(self) -> None:
        # A trava de antes da S-897 só tem o PID: a hora dela é a do arquivo, e um processo que
        # nasceu depois que ela foi escrita não pode ser quem a escreveu.
        trava, _pid = self._trava_de_um_vivo()
        os.utime(trava, (1_000_000_000, 1_000_000_000))
        self.assertFalse(self.abrir().somente_leitura)

    def test_trava_nova_grava_o_pid_e_a_hora_de_criacao(self) -> None:
        livro = self.abrir()
        linhas = (livro.pasta / "caderno.lock").read_text(encoding="utf-8").split()
        self.assertEqual(int(linhas[0]), os.getpid())
        if caderno._inicio_do_processo(os.getpid()) is not None:
            self.assertEqual(float(linhas[1]), caderno._inicio_do_processo(os.getpid()))

    def test_fechar_solta_a_trava(self) -> None:
        livro = self.abrir()
        self.assertTrue((livro.pasta / "caderno.lock").exists())
        livro.fechar()
        self.assertFalse((livro.pasta / "caderno.lock").exists())


class EsperaTests(unittest.TestCase):
    def test_grava_so_com_a_mudanca_e_o_cursor_parados(self) -> None:
        self.assertEqual(caderno.espera_restante(10.0, mudou_em=7.5, cursor_em=8.5), 0.0)
        self.assertAlmostEqual(caderno.espera_restante(10.0, mudou_em=7.5, cursor_em=9.5), 1.0)
        self.assertAlmostEqual(caderno.espera_restante(10.0, mudou_em=9.0, cursor_em=0.0), 1.5)


class LexicoDoLivroTests(_ComLivro):
    """S-903: o léxico do livro grava com a chave com que `lexico.conhecida` confere."""

    def test_palavra_com_eszett_acrescentada_deixa_de_ser_desconhecida(self) -> None:
        from chess_diagram_ocr.text import lexico

        cad = self.abrir()
        texto = "Der Großmeister spielt"
        base = frozenset({"der", "spielt"})
        self.assertEqual([p for _i, _f, p in lexico.desconhecidas(texto, base)], ["Großmeister"])
        self.assertTrue(cad.acrescentar_ao_lexico("Großmeister"))
        self.assertEqual(lexico.desconhecidas(texto, base | cad.lexico()), ())
        self.assertFalse(cad.acrescentar_ao_lexico("GROSSMEISTER"), "é a mesma palavra, e não entra duas vezes")


class AbreDoCadernoTests(unittest.TestCase):
    def estado(self, **campos: object) -> caderno.EstadoDaFolha:
        base: dict[str, object] = {"pagina": 0, "estado": caderno.LIDA, "motor": "auto", "modo_bloco": False}
        base.update(campos)
        return caderno.EstadoDaFolha(**base)  # type: ignore[arg-type]

    def test_o_mesmo_motor_abre_o_caderno(self) -> None:
        self.assertTrue(caderno.abre_do_caderno(self.estado(), motor="auto", modo_bloco=False))

    def test_motor_trocado_sem_correcao_le_de_novo(self) -> None:
        self.assertFalse(caderno.abre_do_caderno(self.estado(), motor="glifo", modo_bloco=False))
        self.assertFalse(caderno.abre_do_caderno(self.estado(), motor="auto", modo_bloco=True))

    def test_com_correcao_ou_conferida_abre_o_caderno_mesmo_com_outro_motor(self) -> None:
        self.assertTrue(caderno.abre_do_caderno(self.estado(correcoes=2, estado=caderno.EDITADA), motor="glifo", modo_bloco=False))
        self.assertTrue(caderno.abre_do_caderno(self.estado(estado=caderno.CONFERIDA), motor="glifo", modo_bloco=False))

    def test_a_pergunta_diz_o_tamanho_da_perda(self) -> None:
        self.assertEqual(
            caderno.frase_de_releitura(11, 7),
            "A folha 12 tem 7 correções. Ler de novo guarda esta versão como anterior e abre a leitura nova.",
        )
        self.assertIn("1 correção.", caderno.frase_de_releitura(0, 1))



def _com_diagrama(livro: str, folha: int) -> rico.DocumentoRico:
    from chess_diagram_ocr.text.pagina import BlocoDeDiagrama

    texto = BlocoDeTexto.de_linhas([LinhaLida(f"antes, folha {folha + 1}", (0.0, 0.0, 9.0, 9.0), 1.0, "camada")])  # type: ignore[arg-type]
    pagina = PaginaLida(
        documento=livro,
        pagina=folha,
        colunas=(Coluna(indice=0, blocos=(texto, BlocoDeDiagrama(indice=0, bbox=(10.0, 10.0, 60.0, 60.0)))),),
    )
    return rico.de_pagina(pagina)


class ExportarFolhasTests(unittest.TestCase):
    """S-614: o caderno inteiro num arquivo, com os exportadores de cada folha intactos."""

    def test_tres_folhas_em_ordem_com_as_imagens_de_cada_uma(self) -> None:
        from chess_diagram_ocr.text import exportacao

        folhas = [_com_diagrama("livro.pdf", 2), _doc(Path("livro.pdf"), 4, "só texto"), _com_diagrama("livro.pdf", 9)]
        recortes = {2: {1: Path("diagramas/x_f0003_d1.png")}, 9: {1: Path("diagramas/x_f0010_d1.png")}}
        relatorio = exportacao.exportar_folhas(
            folhas, exportacao.formato_de(".md"), titulo="livro.pdf — caderno", recortes=recortes, faltam=(0, 1, 3, 5, 6, 7, 8)
        )
        texto = relatorio.conteudo
        posicoes = [texto.index(f"# Folha {n}") for n in (3, 5, 10)]
        self.assertEqual(posicoes, sorted(posicoes), "as folhas saíram fora de ordem")
        self.assertEqual(texto.count("# Folha "), 3, "folha duplicada ou faltando")
        self.assertIn("x_f0003_d1.png", texto)
        self.assertIn("x_f0010_d1.png", texto)
        self.assertLess(texto.index("x_f0003_d1.png"), posicoes[1], "a imagem da folha 3 foi parar noutra folha")
        self.assertEqual(relatorio.diagramas, 2)
        self.assertIn("faltam as folhas 1-2, 4, 6-9", relatorio.avisos)

    def test_a_exportacao_de_uma_folha_nao_mudou(self) -> None:
        """`exportar` agora divide o laço com `exportar_folhas`; a saída de uma folha é a mesma."""
        from chess_diagram_ocr.text import exportacao

        doc = _com_diagrama("livro.pdf", 0)
        um = exportacao.exportar(doc, exportacao.formato_de(".txt"))
        self.assertTrue(um.conteudo.endswith("[Diagrama 1]\n"), um.conteudo)
        self.assertEqual(um.sem_recorte, 1)

    def test_intervalos(self) -> None:
        from chess_diagram_ocr.text.exportacao import intervalos

        self.assertEqual(intervalos([0, 1, 2, 3, 16]), "1-4, 17")
        self.assertEqual(intervalos([5]), "6")
        self.assertEqual(intervalos([]), "")


class IndiceDeFrasesTests(unittest.TestCase):
    def test_a_linha_diz_estado_correcoes_e_data(self) -> None:
        from chess_diagram_ocr.ui.texto_declarado import linha_do_indice

        self.assertEqual(
            linha_do_indice(11, caderno.CONFERIDA, 7, "2026-10-24T14:02:11"), "√ Folha 12 · conferida · 7 correções · 24/10 14:02"
        )
        self.assertEqual(linha_do_indice(0, caderno.EDITADA, 1, ""), "● Folha 1 · corrigida · 1 correção")
        self.assertEqual(linha_do_indice(2, caderno.LIDA, 0, ""), "○ Folha 3 · lida")

    def test_o_rodape_conta_as_conferidas_so_quando_ha(self) -> None:
        from chess_diagram_ocr.ui.texto_declarado import frase_do_rodape

        base = {"folha": 2, "trechos": 4, "diagramas": 0, "miniaturas": 0, "por_gravar": False, "do_caderno": True}
        self.assertIn("34 de 289 folhas conferidas", frase_do_rodape(**base, conferidas=(34, 289)))  # type: ignore[arg-type]
        self.assertNotIn("conferidas", frase_do_rodape(**base, conferidas=(0, 289)))  # type: ignore[arg-type]
        self.assertTrue(frase_do_rodape(**base).startswith("Folha 3 do caderno"))  # type: ignore[arg-type]



class PesquisavelLeOCadernoTests(_ComLivro):
    def test_o_cvoff_pega_so_as_folhas_corrigidas_pedidas_e_sem_travar(self) -> None:
        from chess_diagram_ocr.cli import texto_pesquisavel

        livro = caderno.abrir(self.livro)  # a janela que está corrigindo o livro
        assert livro is not None
        self.addCleanup(livro.fechar)
        livro.gravar(_doc(self.livro, 0, "só lida"))
        livro.gravar(_editado(_doc(self.livro, 1), " corrigida"), correcoes=1)
        livro.gravar(_editado(_doc(self.livro, 7), " fora do pedido"), correcoes=1)
        achadas = texto_pesquisavel._corrigidas_do_caderno(self.livro, [0, 1, 2])
        self.assertEqual(sorted(achadas), [1])
        self.assertIn("corrigida", achadas[1].para_texto())
        self.assertFalse(livro.somente_leitura, "o cvoff tomou a trava da janela")



class LinhaEmTests(unittest.TestCase):
    """S-642, etapa 2: a linha sai da comparação do texto do bloco com as linhas lidas."""

    def doc(self) -> rico.DocumentoRico:
        linhas = [
            LinhaLida("primeira linha do lance", (10.0, 10.0, 200.0, 20.0), 0.9, "glifo"),  # type: ignore[arg-type]
            LinhaLida("segunda linha com Nf3", (10.0, 22.0, 200.0, 32.0), 0.9, "glifo"),  # type: ignore[arg-type]
            LinhaLida("terceira e ultima", (10.0, 34.0, 150.0, 44.0), 0.9, "glifo"),  # type: ignore[arg-type]
        ]
        bloco = BlocoDeTexto.de_linhas(linhas)
        return rico.de_pagina(PaginaLida(documento="l.pdf", pagina=0, colunas=(Coluna(indice=0, blocos=(bloco,)),)))

    def test_cada_linha_pela_posicao(self) -> None:
        doc = self.doc()
        texto = doc.para_texto()
        for indice, palavra in enumerate(("primeira", "Nf3", "ultima")):
            with self.subTest(palavra=palavra):
                self.assertEqual(rico.linha_em(doc, texto.index(palavra) + 1), (0, indice))

    def test_a_linha_continua_achada_depois_de_uma_correcao_pequena(self) -> None:
        doc = self.doc()
        texto = doc.para_texto()
        corrigido = rico.editar(doc, texto.index("Nf3"), texto.index("Nf3") + 3, "Cf3")
        self.assertEqual(rico.linha_em(corrigido, corrigido.para_texto().index("segunda") + 1), (0, 1))

    def test_o_trecho_reescrito_volta_ao_bloco(self) -> None:
        doc = self.doc()
        texto = doc.para_texto()
        inicio = texto.index("segunda")
        reescrito = rico.editar(doc, inicio, inicio + len("segunda linha com Nf3"), "XXXXXXXXXXXXXXXXXXXXXX")
        self.assertIsNone(rico.linha_em(reescrito, inicio + 5))
        self.assertEqual(rico.bloco_em(reescrito, inicio + 5), 0)


class BlocoEmTests(unittest.TestCase):
    """S-642/S-643: do deslocamento no texto ao bloco da página, e de volta."""

    def test_ida_e_volta_por_bloco(self) -> None:
        from chess_diagram_ocr.text.pagina import BlocoDeTexto as Bloco

        blocos = tuple(Bloco.de_linhas([LinhaLida(t, (0.0, 0.0, 9.0, 9.0), 1.0, "glifo")]) for t in ("um", "dois", "três"))  # type: ignore[arg-type]
        doc = rico.de_pagina(PaginaLida(documento="l.pdf", pagina=0, colunas=(Coluna(indice=0, blocos=blocos),)))
        for bloco in range(3):
            comeco = rico.deslocamento_do_bloco(doc, bloco)
            assert comeco is not None
            self.assertEqual(rico.bloco_em(doc, comeco), bloco)
            self.assertEqual(rico.bloco_em(doc, comeco + 1), bloco)
        fim_do_primeiro = len("um")
        self.assertEqual(rico.bloco_em(doc, fim_do_primeiro), 0, "o cursor no fim do parágrafo é dele")
        self.assertEqual(rico.bloco_em(doc, len(doc.para_texto())), 2)
        self.assertIsNone(rico.deslocamento_do_bloco(doc, 9))

    def test_sem_origem_nao_ha_bloco(self) -> None:
        self.assertIsNone(rico.bloco_em(rico.DocumentoRico(), 0))



class DiagramasNoTextoTests(unittest.TestCase):
    """Fase 92, o que é puro: a preferência, o tamanho e alinhar todos os diagramas da folha."""

    def test_a_preferencia_decide_so_a_marca_sem_escolha(self) -> None:
        from chess_diagram_ocr.ui import texto_declarado as td

        self.assertEqual(td.alinhamento_dos_diagramas(td.DIAGRAMAS_AO_CENTRO), "centro")
        self.assertEqual(td.alinhamento_dos_diagramas(td.DIAGRAMAS_A_ESQUERDA), "esquerda")
        self.assertEqual(td.alinhamento_dos_diagramas("de outra versão"), "centro")

    def test_o_tamanho_anda_em_roda_e_o_padrao_e_o_medio(self) -> None:
        from chess_diagram_ocr.ui import texto_declarado as td

        self.assertEqual(td.largura_da_miniatura(""), 240)
        self.assertEqual([td.largura_da_miniatura(t) for t in ("pequeno", "medio", "grande")], [160, 240, 320])
        self.assertEqual(td.proximo_tamanho_da_miniatura("grande"), "pequeno")
        self.assertEqual(td.proximo_tamanho_da_miniatura("medio"), "grande")

    def test_alinhar_os_diagramas_da_folha_e_limpar_a_escolha(self) -> None:
        doc = _com_diagrama("livro.pdf", 0)
        a_esquerda = rico.alinhar_diagramas(doc, "esquerda")
        self.assertEqual([c.atributos.alinhamento for c in a_esquerda.diagramas], ["esquerda"])
        self.assertIs(rico.alinhar_diagramas(a_esquerda, "esquerda"), a_esquerda, "nada mudou e o documento é outro")
        self.assertEqual(rico.diagramas_a_alinhar(a_esquerda, ""), 1)
        self.assertEqual([c.atributos.alinhamento for c in rico.alinhar_diagramas(a_esquerda, "").diagramas], [""])
        texto = [c for c in a_esquerda.corridas if not c.e_diagrama]
        self.assertTrue(all(not c.atributos.alinhamento for c in texto), "o texto em volta foi alinhado junto")

    def test_a_direita_escrita_na_marca_vence_as_duas_preferencias(self) -> None:
        doc = rico.alinhar_diagramas(_com_diagrama("livro.pdf", 0), "direita")
        marca = doc.diagramas[0]
        for padrao in ("centro", "esquerda"):
            self.assertEqual(rico.alinhamento_efetivo(marca, padrao_do_diagrama=padrao), "direita")

    def test_cada_formato_marca_o_centro_e_a_esquerda(self) -> None:
        """S-622: um diagrama centralizado e um à esquerda, em cada formato que alinha."""
        from chess_diagram_ocr.text import exportacao

        doc = _com_diagrama("livro.pdf", 0)
        recortes = {1: Path("d.png")}
        casos = {
            ".html": ('class="alinhar-centro"', 'class="alinhar-esquerda"'),
            ".rtf": ("\\qc", "\\ql"),
            ".md": ('<p align="center">', "![[Diagrama 1]](diagramas/d.png)"),
        }
        for extensao, (centro, esquerda) in casos.items():
            with self.subTest(formato=extensao):
                formato = exportacao.formato_de(extensao)
                self.assertIn(centro, exportacao.exportar(doc, formato, recortes=recortes).conteudo)
                self.assertIn(esquerda, exportacao.exportar(doc, formato, recortes=recortes, diagramas="esquerda").conteudo)


if __name__ == "__main__":
    unittest.main()
