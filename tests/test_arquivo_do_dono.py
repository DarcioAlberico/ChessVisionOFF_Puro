"""A leitura travada (S-812): arquivo do dono que não lê não é arquivo vazio.

Para cada um dos seis leitores: o arquivo corrompido (ou de esquema futuro) é carregado, o valor em
memória é mexido como o programa mexe, e a gravação é pedida. O original tem de estar intacto e a
cópia `.ilegivel-<data>` tem de existir ao lado dele. Antes, os seis voltavam o padrão e a gravação
escrevia o vazio por cima (`scratchpad/defeito_s812.py` da sessão de 2026-11-08: seis FALHA).
"""

from __future__ import annotations

import ast
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from chess_diagram_ocr import arquivo_do_dono, estudo_arquivo, placar, revisao_arquivo, settings
from chess_diagram_ocr import importacao_de_imagens as imp
from chess_diagram_ocr.arquivo_do_dono import (
    EsquemaFuturo,
    GravacaoRecusada,
    Ilegivel,
    Lida,
    VersaoFutura,
    gravavel,
)
from chess_diagram_ocr.config import PROJECT_ROOT
from chess_diagram_ocr.review_queue import carregar_fila, gravar_fila

PGN_EM_CP1252 = (
    '[Event "x"]\n[SourcePDF "Livro.pdf"]\n[Page "3"]\n[Diagram "1"]\n\n1. e4 {an\xe1lise} e5 *\n'
).encode("cp1252")


class SeisLeitoresTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.pasta = Path(tmp.name)

    def _corromper(self, caminho: Path, conteudo: bytes) -> bytes:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(conteudo)
        return conteudo

    def _conferir(self, caminho: Path, original: bytes, gravar: object) -> None:
        with self.assertRaises(GravacaoRecusada) as recusa:
            gravar()  # type: ignore[operator]
        self.assertEqual(original, caminho.read_bytes(), "o original fica intacto")
        copias = sorted(caminho.parent.glob(f"*{arquivo_do_dono.MARCA_DA_COPIA}*"))
        self.assertEqual(1, len(copias), "uma cópia ao lado")
        self.assertEqual(original, copias[0].read_bytes())
        self.assertEqual(caminho.suffix, copias[0].suffix, "a extensão fica no fim")
        self.assertIn(copias[0].name, str(recusa.exception), "a frase diz onde está a cópia")

    def test_settings_com_virgula_sobrando(self) -> None:
        caminho = self.pasta / "settings.json"
        original = self._corromper(caminho, b'{"remote_fen": {"endpoint": "http://x", "enabled": true},}')
        leitura = settings.ler_arquivo(caminho)
        self.assertIsInstance(leitura, Ilegivel)
        self.assertEqual(settings.ConfiguracaoDoArquivo(), leitura.valor, "os padrões valem em memória")
        preferencias = leitura.valor.preferencias
        novo = leitura.valor.com(replace(preferencias, engine=replace(preferencias.engine, multipv=5)))
        self._conferir(caminho, original, lambda: settings.save_settings(replace(leitura, valor=novo)))

    def test_baralho_de_esquema_futuro_com_600_itens(self) -> None:
        caminho = self.pasta / "revisao.json"
        corpo = {"esquema": 2, "itens": [{"chave": f"k{i}"} for i in range(600)]}
        original = self._corromper(caminho, json.dumps(corpo).encode())
        leitura = revisao_arquivo.carregar(caminho=caminho)
        self.assertIsInstance(leitura, EsquemaFuturo)
        self.assertEqual(2, leitura.versao)
        self._conferir(caminho, original, lambda: revisao_arquivo.gravar(leitura))

    def test_placar_truncado(self) -> None:
        caminho = self.pasta / "placar.json"
        original = self._corromper(caminho, b'{"esquema": 1, "livros": [')
        leitura = placar.carregar(caminho=caminho)
        leitura.valor.registrar("um.pdf", placar.CERTO)
        self._conferir(caminho, original, lambda: placar.gravar(leitura))

    def test_sala_com_byte_que_nem_a_cp1252_le(self) -> None:
        """Antes o byte virava U+FFFD em silêncio, e a regravação estragava a análise para sempre.

        O 0x81 é um dos cinco que a cp1252 não define: depois da S-905 é o que sobra de ilegível.
        """
        livro = str(self.pasta / "Livro.pdf")
        caminho = estudo_arquivo.caminho_de(livro, pasta=self.pasta)
        original = self._corromper(caminho, PGN_EM_CP1252.replace(b"\xe1", b"\x81"))
        leitura = estudo_arquivo.carregar(livro, pasta=self.pasta)
        self.assertIsInstance(leitura, Ilegivel)
        self.assertEqual(livro, leitura.valor.documento, "a sala em memória é do livro certo")
        self.assertIn("não é UTF-8 nem ANSI", leitura.mensagem)
        self._conferir(caminho, original, lambda: estudo_arquivo.gravar(leitura))

    def test_sala_em_cp1252_abre_e_regrava_a_analise_com_acento(self) -> None:
        """O PGN que outro programa gravou em ANSI abre, e a gravação o devolve em UTF-8 (S-905)."""
        livro = str(self.pasta / "Livro.pdf")
        caminho = estudo_arquivo.caminho_de(livro, pasta=self.pasta)
        self._corromper(caminho, PGN_EM_CP1252)
        leitura = estudo_arquivo.carregar(livro, pasta=self.pasta)
        self.assertIsInstance(leitura, Lida)
        estudo_arquivo.gravar(leitura)
        self.assertIn("análise", caminho.read_bytes().decode("utf-8"))

    def test_fila_de_revisao_truncada(self) -> None:
        caminho = self.pasta / "review_queue.json"
        original = self._corromper(caminho, b'{"version": 1, "items": [{"page_index": 1')
        leitura = carregar_fila(caminho)
        self._conferir(caminho, original, lambda: gravar_fila(leitura))

    def test_lote_de_versao_futura_nao_recomeca_tudo_pendente(self) -> None:
        imagens = self.pasta / "imgs"
        imagens.mkdir()
        lotes = self.pasta / "lotes"
        caminho = imp.caminho_do_lote(imagens, imp.SEM_FEN, diretorio=lotes)
        original = self._corromper(caminho, b'{"versao": 9, "itens": []}')
        leitura = imp.abrir_lote(imagens, imp.SEM_FEN, diretorio=lotes)
        self.assertIsInstance(leitura, EsquemaFuturo)
        self.assertEqual(caminho, leitura.caminho)
        self._conferir(caminho, original, lambda: imp.gravar_lote(gravavel(leitura)))

    def test_outro_lote_ilegivel_nao_vira_copia_de_copia(self) -> None:
        """A herança entre lotes varre a pasta: a cópia `.ilegivel` não pode ser lida como lote."""
        imagens = self.pasta / "imgs"
        imagens.mkdir()
        lotes = self.pasta / "lotes"
        lotes.mkdir()
        (lotes / "outro.json").write_bytes(b"{")
        imp.abrir_lote(imagens, imp.SEM_FEN, diretorio=lotes)
        imp.abrir_lote(imagens, imp.SEM_FEN, diretorio=lotes)
        nomes = sorted(p.name for p in lotes.iterdir())
        self.assertEqual(1, sum(arquivo_do_dono.MARCA_DA_COPIA in nome for nome in nomes), nomes)


class LeituraTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.caminho = Path(tmp.name) / "dados.json"

    def _ler(self) -> arquivo_do_dono.Leitura[dict[str, object]]:
        def interpretar(texto: str) -> dict[str, object]:
            dados = json.loads(texto)
            if dados.get("esquema", 1) > 1:
                raise VersaoFutura(dados["esquema"])
            return dict(dados)

        return arquivo_do_dono.ler(self.caminho, interpretar, dict)

    def test_ausente_e_lida_com_o_padrao(self) -> None:
        leitura = self._ler()
        self.assertIsInstance(leitura, Lida)
        self.assertEqual({}, leitura.valor)
        self.assertEqual([], list(self.caminho.parent.iterdir()), "ausência não cria nada")

    def test_lida_grava_e_ilegivel_nao(self) -> None:
        self.caminho.write_text('{"a": 1}', encoding="utf-8")
        self.assertIs(gravavel(self._ler()).valor["a"], 1)

    def test_reabrir_no_mesmo_dia_nao_multiplica_copias(self) -> None:
        self.caminho.write_bytes(b"{")
        for _vez in range(3):
            self.assertIsInstance(self._ler(), Ilegivel)
        self.assertEqual(1, len(list(self.caminho.parent.glob("*.ilegivel-*"))))

    def test_copia_de_conteudo_diferente_no_mesmo_dia_nao_e_sobrescrita(self) -> None:
        dia = date(2026, 11, 8)
        self.caminho.write_bytes(b"{")
        primeira = arquivo_do_dono.copiar_ao_lado(self.caminho, hoje=dia)
        self.caminho.write_bytes(b"[")
        segunda = arquivo_do_dono.copiar_ao_lado(self.caminho, hoje=dia)
        assert primeira is not None and segunda is not None
        self.assertEqual("dados.ilegivel-2026-11-08.json", primeira.name)
        self.assertEqual("dados.ilegivel-2026-11-08-2.json", segunda.name)
        self.assertEqual(b"{", primeira.read_bytes())

    def test_leitura_parcial_entra_em_memoria_e_trava(self) -> None:
        """O caminho que a S-814 e a S-896 vão usar: o que leu fica, e a gravação continua travada."""
        self.caminho.write_text("x", encoding="utf-8")

        def interpretar(_texto: str) -> list[int]:
            raise arquivo_do_dono.ConteudoIlegivel("a terceira partida não leu", parcial=[1, 2])

        leitura = arquivo_do_dono.ler(self.caminho, interpretar, list)
        self.assertIsInstance(leitura, Ilegivel)
        self.assertEqual([1, 2], leitura.valor)
        self.assertIn("a terceira partida não leu", leitura.mensagem)


SEIS_MODULOS = (
    "settings",
    "revisao_arquivo",
    "placar",
    "estudo_arquivo",
    "review_queue",
    "importacao_de_imagens",
)
LEITURAS_QUE_NAO_SAO_DO_DONO = {("importacao_de_imagens", "ler_relatorios_do_chessmeridaocr")}
"""O relatório HTML do ChessMeridaOCR é do plugin de outra pessoa: o programa só o lê, nunca o grava."""


class GuardaTests(unittest.TestCase):
    """Nenhum leitor de arquivo do dono lê o arquivo por fora de `arquivo_do_dono.ler`."""

    def _arvore(self, modulo: str) -> ast.Module:
        caminho = PROJECT_ROOT / "src" / "chess_diagram_ocr" / f"{modulo}.py"
        return ast.parse(caminho.read_text(encoding="utf-8"))

    def test_os_seis_leem_pelo_ler(self) -> None:
        chamadas = 0
        for modulo in SEIS_MODULOS:
            daqui = sum(
                1
                for no in ast.walk(self._arvore(modulo))
                if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == "ler"
            )
            self.assertGreaterEqual(daqui, 1, f"{modulo} não lê pelo arquivo_do_dono.ler")
            chamadas += daqui
        self.assertGreaterEqual(chamadas, 6, "piso de seis: a guarda não pode passar vazia")

    def test_nenhum_le_o_arquivo_por_fora(self) -> None:
        achados = []
        for modulo in SEIS_MODULOS:
            for funcao in ast.walk(self._arvore(modulo)):
                if not isinstance(funcao, ast.FunctionDef) or (modulo, funcao.name) in LEITURAS_QUE_NAO_SAO_DO_DONO:
                    continue
                for no in ast.walk(funcao):
                    if (
                        isinstance(no, ast.Call)
                        and isinstance(no.func, ast.Attribute)
                        and no.func.attr in ("read_text", "read_bytes")
                    ):
                        achados.append(f"{modulo}.{funcao.name}:{no.lineno}")
        self.assertEqual([], achados)


class LerTextoTests(unittest.TestCase):
    """`ler_texto` (S-905): o arquivo que passou pelo Bloco de Notas abre, e o do programa não levanta."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.caminho = Path(tmp.name) / "arquivo.txt"

    def _ler(self, dados: bytes, *, do_usuario: bool = True) -> str:
        self.caminho.write_bytes(dados)
        return arquivo_do_dono.ler_texto(self.caminho, do_usuario=do_usuario)

    def test_as_quatro_formas_do_bloco_de_notas_dao_o_mesmo_texto(self) -> None:
        texto = "José\nanálise\n"
        for nome, dados in (
            ("utf-8", texto.encode("utf-8")),
            ("utf-8 com BOM", texto.encode("utf-8-sig")),
            ("ansi", texto.encode("cp1252")),
            ("utf-16 le", texto.encode("utf-16")),
            ("utf-16 be", b"\xfe\xff" + texto.encode("utf-16-be")),
        ):
            with self.subTest(nome):
                self.assertEqual(texto, self._ler(dados))

    def test_o_que_nem_a_cp1252_le_e_ilegivel_com_o_byte_no_motivo(self) -> None:
        with self.assertRaises(arquivo_do_dono.ArquivoIlegivel) as erro:
            self._ler(b"abc \x81 def")
        self.assertIsInstance(erro.exception, ValueError, "cai em todo except (OSError, ValueError)")
        self.assertIn("b'\\x81'", str(erro.exception))
        with self.assertRaises(arquivo_do_dono.ArquivoIlegivel):
            self._ler(b"\xff\xfea\x00b")  # UTF-16 de tamanho ímpar

    def test_arquivo_do_programa_estraga_so_o_byte_rasgado(self) -> None:
        dados = b"linha boa\nan" + "á".encode()[:1] + b"\nlinha boa\n"
        self.assertEqual("linha boa\nan\ufffd\nlinha boa\n", self._ler(dados, do_usuario=False))
        self.assertEqual("ab", self._ler(b"\xef\xbb\xbfab", do_usuario=False), "o BOM sai também")


PACOTE = Path(arquivo_do_dono.__file__).parent
"""O pacote que foi importado, e não `PROJECT_ROOT`: num worktree os dois podem ser diferentes."""

LEITURAS_ESTRITAS = {
    ("cli/audit.py", "violacoes_do_texto"): "relatório que o próprio programa gravou, lido pela linha de comando",
    ("field_eval.py", "_imports_of"): "código-fonte do repositório, lido para o fecho de importação",
    ("text_status.py", "_define_no_topo"): "código-fonte do repositório",
    ("qt/__init__.py", "dialogos_do_produto"): "código-fonte do repositório",
    ("text/caderno.py", "_inicio_do_processo"): "o /proc do Linux, que não é arquivo de ninguém",
    ("text/caderno.py", "_ler_trava"): "a trava do processo: o programa a grava, e só ele a lê",
    ("text/caderno.py", "_gravar_conferido"): "a conferência, igual por igual, do temporário que acabou de ser gravado",
    ("marcas_de_casa.py", "_ler"): "o dataset de marcas: o arquivo que não lê levanta ValueError alto, de propósito",
    ("text/modelo.py", "ler_metadado"): "metadado que o treino gravou: byte errado é modelo ilegível, e recusa",
    ("text/onnx_glifos.py", "ler_metadado_onnx"): "metadado que o treino gravou: byte errado é modelo ilegível, e recusa",
}
"""Leituras num `try` que ficam fora de `ler_texto`, e por quê: nenhuma é arquivo que a pessoa edite ou escolha."""


def _nomes_do_except(tratador: ast.ExceptHandler) -> set[str]:
    tipos = tratador.type.elts if isinstance(tratador.type, ast.Tuple) else [tratador.type]
    return {t.attr if isinstance(t, ast.Attribute) else getattr(t, "id", "") for t in tipos if t is not None}


def _eh_leitura_de_texto(no: ast.AST) -> bool:
    """`p.read_text(...)` ou `p.read_bytes().decode(...)`."""
    if not isinstance(no, ast.Call) or not isinstance(no.func, ast.Attribute):
        return False
    if no.func.attr == "read_text":
        return True
    alvo = no.func.value
    return (
        no.func.attr == "decode"
        and isinstance(alvo, ast.Call)
        and isinstance(alvo.func, ast.Attribute)
        and alvo.func.attr == "read_bytes"
    )


def achados_da_s905(fonte: str) -> tuple[list[int], dict[int, str]]:
    """As duas coisas que a guarda da S-905 procura numa fonte.

    - as linhas dos `except` que nomeiam `JSONDecodeError` sem `ValueError` -- e o
      `UnicodeDecodeError`, que é `ValueError` e não `JSONDecodeError`, passa por eles;
    - as leituras de texto dentro do corpo de um `try`, pela linha, com a função mais interna
      em volta (`<módulo>` fora de função). Quem põe a leitura num `try` está prometendo
      tolerância, e a tolerância mora em `ler_texto`.
    """
    arvore = ast.parse(fonte)
    excepts = [
        tratador.lineno
        for tratador in ast.walk(arvore)
        if isinstance(tratador, ast.ExceptHandler)
        and tratador.type is not None
        and "JSONDecodeError" in (nomes := _nomes_do_except(tratador))
        and "ValueError" not in nomes
    ]
    leituras: dict[int, str] = {}
    escopos: list[tuple[str, ast.AST]] = [("<módulo>", arvore)]
    escopos += [(f.name, f) for f in ast.walk(arvore) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for nome, escopo in escopos:  # o `ast.walk` vai de fora para dentro: a função mais interna fica
        for tentativa in ast.walk(escopo):
            if isinstance(tentativa, ast.Try):
                for comando in tentativa.body:
                    for no in ast.walk(comando):
                        if _eh_leitura_de_texto(no):
                            leituras[no.lineno] = nome
    return excepts, leituras


class GuardaDaS905Tests(unittest.TestCase):
    """Nenhum `except` deixa `UnicodeDecodeError` passar, e a leitura tolerante passa por `ler_texto`."""

    def _varrer(self) -> tuple[list[str], list[str], set[tuple[str, str]]]:
        excepts: list[str] = []
        leituras: list[str] = []
        vistas: set[tuple[str, str]] = set()
        for arquivo in sorted(PACOTE.rglob("*.py")):
            relativo = arquivo.relative_to(PACOTE).as_posix()
            linhas, lidas = achados_da_s905(arquivo.read_text(encoding="utf-8"))
            excepts += [f"{relativo}:{linha}" for linha in linhas]
            for linha, funcao in lidas.items():
                if relativo == "arquivo_do_dono.py":
                    continue
                if (relativo, funcao) in LEITURAS_ESTRITAS:
                    vistas.add((relativo, funcao))
                else:
                    leituras.append(f"{relativo}:{linha} ({funcao})")
        return excepts, leituras, vistas

    def test_nenhum_except_de_json_sem_valueerror(self) -> None:
        excepts, _leituras, _vistas = self._varrer()
        self.assertEqual([], excepts)

    def test_leitura_num_try_passa_por_ler_texto(self) -> None:
        _excepts, leituras, vistas = self._varrer()
        self.assertEqual([], leituras)
        self.assertEqual(set(LEITURAS_ESTRITAS), vistas, "exceção que não acha mais nada sai da lista")

    def test_a_guarda_acha_o_que_procura(self) -> None:
        """Piso: a guarda não pode passar verde por não saber olhar."""
        fonte = (
            "import json\n"
            "def carregar(p):\n"
            "    try:\n"
            "        return json.loads(p.read_text(encoding='utf-8'))\n"
            "    except (OSError, json.JSONDecodeError):\n"
            "        return {}\n"
            "def bruto(p):\n"
            "    try:\n"
            "        return p.read_bytes().decode('utf-8')\n"
            "    except (OSError, ValueError):\n"
            "        return ''\n"
            "def certo(p):\n"
            "    texto = p.read_text(encoding='utf-8')\n"
            "    try:\n"
            "        return json.loads(texto)\n"
            "    except json.JSONDecodeError as e:\n"
            "        raise ValueError(e)\n"
        )
        excepts, leituras = achados_da_s905(fonte)
        self.assertEqual([5, 16], excepts)
        self.assertEqual({4: "carregar", 9: "bruto"}, leituras)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
