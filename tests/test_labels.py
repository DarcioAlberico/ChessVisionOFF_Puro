"""A porta única para o `labels.csv` (S-51).

Dois testes carregam este arquivo, e os dois protegem 3.313 rótulos de trabalho humano.

`test_a_saida_e_byte_a_byte_igual_a_do_pandas` é o critério de aceite literal: a
implementação mudou de pandas para o `csv` da biblioteca padrão, e o que não pode mudar é o
arquivo. Um espaço a mais na aspa de uma FEN transformaria a próxima gravação num diff de
3.313 linhas.

`test_nenhum_modulo_fora_daqui_le_ou_escreve_o_csv_de_rotulos` é o critério que impede a
sexta porta de aparecer. Cinco eram conhecidas quando a S-51 foi escrita; a varredura achou
uma sexta em `review_queue.rare_classes_from_labels`, que ninguém tinha listado.
"""

from __future__ import annotations

import inspect
import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from chess_diagram_ocr import labels as labels_module
from chess_diagram_ocr.labels import (
    LABEL_COLUMNS,
    SCHEMA_CURRENT,
    SCHEMA_LEGACY,
    DatasetEntry,
    LabelStore,
    render_csv,
)

SRC = Path(labels_module.__file__).resolve().parent

LEGAL = "8/8/8/8/8/8/4K3/4k3 w - - 0 1"


def entry(name: str, **campos: str) -> DatasetEntry:
    return DatasetEntry(filename=name, fen=LEGAL, **campos)


class RoundTripTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.csv = Path(self.pasta.name) / "labels.csv"

    def test_gravar_e_ler_devolve_o_mesmo(self) -> None:
        store = LabelStore(self.csv)
        original = [
            entry("a.png", side_to_move="w", source_pdf="livro.pdf", source_page="20"),
            entry("b.png", side_to_move="b", corrected_by="ocr-corrigido"),
        ]
        store.rewrite(original)

        self.assertEqual(store.read(), original)

    def test_arquivo_ausente_le_como_vazio(self) -> None:
        """Não é caso de erro: é o primeiro uso do projeto numa máquina nova."""
        self.assertEqual(LabelStore(self.csv).read(), [])
        self.assertEqual(LabelStore(self.csv).read_pairs(), [])

    def test_esquema_antigo_continua_carregando(self) -> None:
        """`filename,fen` é o esquema do primeiro commit. 3.195 rótulos vieram dele."""
        self.csv.write_text(f"filename,fen\na.png,{LEGAL}\n", encoding="utf-8")
        store = LabelStore(self.csv)

        self.assertEqual(store.schema_version, SCHEMA_LEGACY)
        self.assertEqual(store.read(), [DatasetEntry(filename="a.png", fen=LEGAL)])

        # E ganha as colunas da S-19, vazias, na primeira gravacao.
        store.append(entry("b.png"))
        self.assertEqual(store.schema_version, SCHEMA_CURRENT)

    def test_coluna_obrigatoria_ausente_e_erro(self) -> None:
        self.csv.write_text("filename,turno\na.png,w\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            LabelStore(self.csv).read()

    def test_coluna_extra_sobrevive_a_uma_gravacao(self) -> None:
        """É o que a quarentena precisa: uma porta que descartasse `motivo` o perderia."""
        store = LabelStore(self.csv)
        store.rewrite([{"filename": "a.png", "fen": LEGAL, "motivo": "rei faltando"}])
        store.append(entry("b.png"))

        rows = store.read_rows()
        self.assertEqual(rows[0]["motivo"], "rei faltando")
        self.assertIn("motivo", store.columns())

    def test_inteiro_com_ponto_converge_na_gravacao(self) -> None:
        """A S-58: `20.0` vira `20`, e o arquivo converge sem comando de migração."""
        store = LabelStore(self.csv)
        store.rewrite([{"filename": "a.png", "fen": LEGAL, "source_page": "20.0", "source_diagram": "1.0"}])
        store.append(entry("b.png"))

        self.assertEqual(store.read()[0].source_page, "20")
        self.assertEqual(store.read()[0].source_diagram, "1")

    def test_nan_herdado_de_um_arquivo_antigo_vira_vazio(self) -> None:
        """`"nan"` existe gravado: é o que sobrava de um CSV lido sem `keep_default_na`."""
        self.csv.write_text(f"filename,fen,source_pdf\na.png,{LEGAL},nan\n", encoding="utf-8")
        self.assertEqual(LabelStore(self.csv).read()[0].source_pdf, "")


class ByteCompatibilityTests(unittest.TestCase):
    """O critério de aceite: a implementação mudou, o arquivo não pode mudar."""

    CASOS = [
        {"filename": "a.png", "fen": LEGAL},
        # Virgula: e o caractere que o CSV usa como separador, e a legenda pode te-lo.
        {"filename": "b.png", "fen": LEGAL, "source_pdf": "Euwe, Kramer - Das Mittelspiel.pdf"},
        # Aspas: o escape e por duplicacao, e as duas implementacoes tem de concordar.
        {"filename": "c.png", "fen": LEGAL, "corrected_by": 'ele disse "ok"'},
        # Acentuacao: o acervo tem portugues, espanhol e alemao.
        {"filename": "d.png", "fen": LEGAL, "source_pdf": "La Combinación en Ajedrez.pdf"},
        # Quebra de linha dentro da celula: legenda de PDF pode traze-la.
        {"filename": "e.png", "fen": LEGAL, "corrected_by": "linha1\nlinha2"},
        {"filename": "f.png", "fen": LEGAL, "source_page": "20.0", "source_diagram": "1.0"},
        {"filename": "g.png", "fen": LEGAL, "motivo": "coluna, extra"},
    ]

    def pandas_render(self, rows: list[dict[str, str]]) -> str:
        """O `_write_labels` que a S-51 substituiu, reproduzido linha a linha."""
        frame = pd.DataFrame(rows).fillna("")
        for column in LABEL_COLUMNS:
            if column not in frame.columns:
                frame[column] = ""
        for column in ("source_page", "source_diagram"):
            frame[column] = frame[column].map(labels_module._as_integer_text)
        extra = [column for column in frame.columns if column not in LABEL_COLUMNS]
        return str(frame[[*LABEL_COLUMNS, *extra]].fillna("").to_csv(index=False, lineterminator=os.linesep))

    def test_a_saida_e_byte_a_byte_igual_a_do_pandas(self) -> None:
        self.assertEqual(render_csv(self.CASOS), self.pandas_render(self.CASOS))

    def test_cada_caso_isolado_tambem(self) -> None:
        """Junto pode esconder: um caso que erra e outro que compensa dariam o mesmo total."""
        for caso in self.CASOS:
            with self.subTest(filename=caso["filename"]):
                self.assertEqual(render_csv([caso]), self.pandas_render([caso]))

    def test_o_que_foi_gravado_le_de_volta_igual(self) -> None:
        """Byte-compatível com o pandas **e** com si mesmo -- as duas coisas são precisas."""
        with tempfile.TemporaryDirectory() as pasta:
            csv_path = Path(pasta) / "labels.csv"
            store = LabelStore(csv_path)
            store.rewrite(self.CASOS)
            # `read_bytes` e nao `read_text`: a leitura de texto traduz `\r\n` para `\n`, e
            # o terminador de linha e justamente uma das coisas que este teste protege.
            self.assertEqual(render_csv(store.read_rows()).encode("utf-8"), csv_path.read_bytes())


class MutationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.csv = Path(self.pasta.name) / "labels.csv"
        self.store = LabelStore(self.csv)
        self.store.rewrite([entry("a.png"), entry("b.png"), entry("c.png")])

    def test_append_preserva_a_ordem(self) -> None:
        self.store.append(entry("d.png"))
        self.assertEqual([e.filename for e in self.store.read()], ["a.png", "b.png", "c.png", "d.png"])

    def test_update_devolve_falso_para_quem_nao_existe(self) -> None:
        self.assertFalse(self.store.update("z.png", fen=LEGAL))

    def test_update_troca_so_os_campos_pedidos(self) -> None:
        self.store.update("b.png", corrected_by="fila-revisao")
        lidas = {e.filename: e for e in self.store.read()}

        self.assertEqual(lidas["b.png"].corrected_by, "fila-revisao")
        self.assertEqual(lidas["b.png"].fen, LEGAL)
        self.assertEqual(lidas["a.png"].corrected_by, "")

    def test_remove_devolve_quantas_sairam(self) -> None:
        self.assertEqual(self.store.remove(["a.png", "z.png"]), 1)
        self.assertEqual([e.filename for e in self.store.read()], ["b.png", "c.png"])

    def test_remove_de_nada_nao_toca_o_arquivo(self) -> None:
        antes = self.csv.read_bytes()
        self.assertEqual(self.store.remove([]), 0)
        self.assertEqual(self.csv.read_bytes(), antes)


class TransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.csv = Path(self.pasta.name) / "labels.csv"
        self.store = LabelStore(self.csv)
        self.store.rewrite([entry(f"{i}.png") for i in range(5)])

        self.gravacoes: list[bytes] = []
        original = labels_module.atomic_write_bytes

        def contando(path: Path, payload: bytes) -> None:
            self.gravacoes.append(payload)
            original(path, payload)

        labels_module.atomic_write_bytes = contando  # type: ignore[assignment]
        self.addCleanup(lambda: setattr(labels_module, "atomic_write_bytes", original))

    def test_uma_gravacao_no_fim_e_nao_uma_por_operacao(self) -> None:
        """A aba Dataset regravava as 3.313 linhas a cada correção. Vinte correções, vinte."""
        with self.store.transaction() as tx:
            for i in range(5):
                tx.update(f"{i}.png", corrected_by="dataset-recorrigido")

        self.assertEqual(len(self.gravacoes), 1)
        self.assertTrue(all(e.corrected_by == "dataset-recorrigido" for e in self.store.read()))

    def test_dentro_da_transacao_a_leitura_ja_ve_o_pendente(self) -> None:
        with self.store.transaction() as tx:
            tx.update("0.png", corrected_by="x")
            self.assertEqual(tx.read()[0].corrected_by, "x")
            # E o arquivo em disco ainda nao.
            self.assertEqual(LabelStore(self.csv).read()[0].corrected_by, "")

    def test_excecao_descarta_tudo_e_nao_toca_o_arquivo(self) -> None:
        antes = self.csv.read_bytes()
        with self.assertRaises(RuntimeError), self.store.transaction() as tx:
            tx.remove(["0.png", "1.png"])
            raise RuntimeError("algo deu errado no meio")

        self.assertEqual(self.gravacoes, [])
        self.assertEqual(self.csv.read_bytes(), antes)

    def test_transacao_aninhada_e_recusada(self) -> None:
        """Sem journal, aninhar daria a impressão de um rollback parcial que não existe."""
        with self.store.transaction(), self.assertRaises(RuntimeError):
            with self.store.transaction():
                pass

    def test_o_store_volta_a_funcionar_depois_de_uma_transacao_que_falhou(self) -> None:
        with self.assertRaises(ValueError), self.store.transaction() as tx:
            tx.remove(["0.png"])
            raise ValueError("boom")

        self.store.append(entry("novo.png"))
        self.assertEqual(len(self.store.read()), 6)


class MoveToTests(unittest.TestCase):
    """A quarentena, que é a única operação entre dois arquivos de rótulo."""

    def setUp(self) -> None:
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        raiz = Path(self.pasta.name)
        self.store = LabelStore(raiz / "labels.csv")
        self.quarentena = LabelStore(raiz / "quarantine.csv")
        self.store.rewrite([entry("a.png"), entry("b.png"), entry("c.png")])

    def test_a_linha_sai_de_um_e_chega_no_outro(self) -> None:
        movidas = self.store.move_to(self.quarentena, ["b.png"], extra={"motivo": "ilegal"})

        self.assertEqual(len(movidas), 1)
        self.assertEqual([e.filename for e in self.store.read()], ["a.png", "c.png"])
        self.assertEqual(self.quarentena.read_rows()[0]["motivo"], "ilegal")

    def test_motivo_por_linha_pela_forma_de_funcao(self) -> None:
        """É o que a auditoria precisa: cada rótulo ilegal tem os problemas dele."""
        problemas = {"a.png": "rei branco faltando", "c.png": "peão na primeira fila"}
        self.store.move_to(self.quarentena, problemas.keys(), extra=lambda nome: {"motivo": problemas[nome]})

        motivos = {row["filename"]: row["motivo"] for row in self.quarentena.read_rows()}
        self.assertEqual(motivos, problemas)

    def test_a_volta_remove_a_coluna_motivo_em_vez_de_esvazia_la(self) -> None:
        """Coluna vazia continua sendo coluna, e mentiria para as 3.313 linhas restantes."""
        self.store.move_to(self.quarentena, ["b.png"], extra={"motivo": "ilegal"})
        self.quarentena.move_to(self.store, ["b.png"], drop=("motivo",))

        self.assertNotIn("motivo", self.store.columns())
        self.assertEqual([e.filename for e in self.store.read()], ["a.png", "c.png", "b.png"])

    def test_nome_que_nao_existe_nao_move_nada(self) -> None:
        self.assertEqual(self.store.move_to(self.quarentena, ["z.png"]), [])
        self.assertFalse(self.quarentena.exists())


class BackupTests(unittest.TestCase):
    def test_backup_copia_byte_a_byte(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            csv_path = Path(pasta) / "labels.csv"
            store = LabelStore(csv_path)
            store.rewrite([entry("a.png")])

            destino = store.backup()
            self.assertTrue(destino.name.startswith("labels.csv.bak-"))
            self.assertEqual(destino.read_bytes(), csv_path.read_bytes())

    def test_backup_de_arquivo_que_nao_existe_levanta(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            with self.assertRaises(FileNotFoundError):
                LabelStore(Path(pasta) / "labels.csv").backup()

    def test_dois_backups_no_mesmo_segundo_nao_se_apagam(self) -> None:
        """`move_to` faz backup da origem e do destino em sequência (S-375)."""
        from unittest.mock import patch as _patch

        from chess_diagram_ocr import labels as labels_mod

        with tempfile.TemporaryDirectory() as pasta:
            csv_path = Path(pasta) / "labels.csv"
            store = LabelStore(csv_path)
            store.rewrite([entry("a.png")])

            with _patch.object(labels_mod, "datetime") as relogio:
                relogio.now.return_value.strftime.return_value = "20260828_120000"
                primeiro = store.backup()
                conteudo_do_primeiro = primeiro.read_bytes()
                store.rewrite([entry("a.png"), entry("b.png")])
                segundo = store.backup()

            self.assertNotEqual(primeiro, segundo)
            self.assertEqual(primeiro.read_bytes(), conteudo_do_primeiro, "o primeiro não pode ser sobrescrito")
            self.assertEqual(segundo.name, f"{primeiro.name}-2")

    def test_copia_interrompida_nao_deixa_backup_pela_metade(self) -> None:
        """Um `.bak-` truncado se parece com um backup e não é."""
        from unittest.mock import patch as _patch

        with tempfile.TemporaryDirectory() as pasta:
            csv_path = Path(pasta) / "labels.csv"
            store = LabelStore(csv_path)
            store.rewrite([entry("a.png")])

            with _patch("os.fsync", side_effect=OSError("disco cheio")), self.assertRaises(OSError):
                store.backup()

            self.assertEqual(list(Path(pasta).glob("*.bak-*")), [])


class BomDoExcelTests(unittest.TestCase):
    """Três bytes invisíveis tornavam o dataset inteiro ilegível (S-374).

    O `labels.csv` é um arquivo que gente abre numa planilha, e o Excel salva "CSV UTF-8" com
    BOM. A primeira coluna deixava de se chamar `filename` e a mensagem de erro listava dois
    conjuntos que se leem iguais na tela.
    """

    def _com_bom(self, pasta: str) -> Path:
        csv_path = Path(pasta) / "labels.csv"
        store = LabelStore(csv_path)
        store.rewrite([entry("a.png")])
        csv_path.write_bytes(b"\xef\xbb\xbf" + csv_path.read_bytes())
        return csv_path

    def test_o_csv_salvo_pelo_excel_continua_legivel(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            store = LabelStore(self._com_bom(pasta))
            self.assertEqual([linha["filename"] for linha in store.read_rows()], ["a.png"])

    def test_as_colunas_saem_sem_o_bom_grudado_na_primeira(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            self.assertEqual(LabelStore(self._com_bom(pasta)).columns()[0], "filename")

    def test_reescrever_nao_devolve_o_bom_ao_arquivo(self) -> None:
        """Ler aceita os dois; escrever continua em `utf-8` puro, para quem lê de fora."""
        with tempfile.TemporaryDirectory() as pasta:
            csv_path = self._com_bom(pasta)
            store = LabelStore(csv_path)
            store.rewrite(store.read_rows())
            self.assertFalse(csv_path.read_bytes().startswith(b"\xef\xbb\xbf"))


class SinglePortTests(unittest.TestCase):
    """O critério que impede a sexta porta de aparecer."""

    def arquivos(self) -> list[Path]:
        """Todo o código do projeto, incluindo as duas telas na raiz.

        `splits.py` **não** é exceção: ele cuida do `splits.csv`, que é outro arquivo com
        outro dono, e na S-51 ele também deixou de usar pandas -- por um motivo próprio, que
        é a escrita atômica. Um arquivo que carrega a fronteira entre treino e teste não
        podia ser gravado com `to_csv` direto no destino.
        """
        raiz = SRC.parents[1]
        return [*sorted(SRC.rglob("*.py")), raiz / "app_pyqt.py", raiz / "examples" / "streamlit_demo.py"]

    def test_nenhum_modulo_fora_daqui_le_ou_escreve_o_csv_de_rotulos(self) -> None:
        culpados: list[str] = []
        for arquivo in self.arquivos():
            if arquivo.name == "labels.py":
                continue
            texto = arquivo.read_text(encoding="utf-8")
            # Fora de comentario e docstring: o `labels.py` e o `audit.py` citam `to_csv` em
            # prosa para explicar o defeito que a S-51 fecha, e proibir a palavra proibiria
            # a explicacao.
            for numero, linha in enumerate(texto.splitlines(), start=1):
                despida = linha.strip()
                if despida.startswith("#") or despida.startswith(('"', "'")):
                    continue
                if "read_csv(" in despida or "to_csv(" in despida:
                    culpados.append(f"{arquivo.name}:{numero}: {despida}")

        self.assertEqual(culpados, [], "\n".join(["Acesso ao CSV fora do LabelStore:", *culpados]))

    def test_o_labels_py_nao_importa_pandas(self) -> None:
        """A S-58 existe porque o pandas infere tipo. Sem pandas, não há o que inferir.

        A palavra aparece na prosa do módulo, que explica exatamente isso -- por isso o teste
        olha as linhas de `import` e não o texto inteiro.
        """
        importes = [
            linha
            for linha in (SRC / "labels.py").read_text(encoding="utf-8").splitlines()
            if linha.startswith(("import ", "from "))
        ]
        self.assertEqual([linha for linha in importes if "pandas" in linha], [])



class LabelRouteTests(unittest.TestCase):
    """`corrected_by`: por qual caminho a amostra chegou ao rótulo (S-52).

    Mora fora do painel para poder ser testada sem abrir uma janela do Tk -- é a mesma regra
    que organizou a Fase 6, e é o que permite exercitar a ordem de precedência inteira aqui.
    """

    LIDO = "4k3/8/8/8/8/8/8/4K3"
    CORRIGIDO = "4k3/8/8/8/8/8/8/3QK3"

    def test_salvar_sem_mexer_e_ocr_aceito(self) -> None:
        rota = labels_module.label_route(read_placement=self.LIDO, saved_placement=f"{self.LIDO} w - - 0 1")
        self.assertEqual(rota, labels_module.OCR_ACEITO)

    def test_uma_casa_diferente_ja_e_ocr_corrigido(self) -> None:
        rota = labels_module.label_route(read_placement=self.LIDO, saved_placement=f"{self.CORRIGIDO} w - - 0 1")
        self.assertEqual(rota, labels_module.OCR_CORRIGIDO)

    def test_so_o_lado_a_jogar_mudar_nao_e_correcao_de_leitura(self) -> None:
        """O campo de peças é o que o modelo leu; a vez vem da S-16/S-17, não dele."""
        rota = labels_module.label_route(read_placement=self.LIDO, saved_placement=f"{self.LIDO} b - - 0 1")
        self.assertEqual(rota, labels_module.OCR_ACEITO)

    def test_a_net_vence_a_comparacao_de_pecas(self) -> None:
        """Leitura de terceiro não pode ser contada como trabalho humano de correção."""
        rota = labels_module.label_route(
            from_net=True, read_placement=self.LIDO, saved_placement=self.CORRIGIDO
        )
        self.assertEqual(rota, labels_module.NET_REMOTO)

    def test_a_fila_vence_a_comparacao_de_pecas(self) -> None:
        rota = labels_module.label_route(
            from_queue=True, read_placement=self.LIDO, saved_placement=self.CORRIGIDO
        )
        self.assertEqual(rota, labels_module.FILA_REVISAO)

    def test_a_net_vence_a_fila(self) -> None:
        """Precedência do mais específico: os dois podem valer, e a Net é o que aconteceu."""
        rota = labels_module.label_route(from_net=True, from_queue=True)
        self.assertEqual(rota, labels_module.NET_REMOTO)

    def test_recorrecao_pela_aba_dataset(self) -> None:
        self.assertEqual(labels_module.label_route(from_dataset=True), labels_module.DATASET_RECORRIGIDO)

    def test_toda_rota_esta_no_vocabulario(self) -> None:
        combinacoes = [
            {},
            {"from_net": True},
            {"from_queue": True},
            {"from_dataset": True},
            {"read_placement": self.LIDO, "saved_placement": self.CORRIGIDO},
        ]
        for kwargs in combinacoes:
            with self.subTest(**kwargs):
                self.assertIn(labels_module.label_route(**kwargs), labels_module.CORRECTED_BY_VALUES)

class LabelOriginsTests(unittest.TestCase):
    """A tripla de procedência que o agrupamento por diagrama impresso usa (S-98)."""

    def _grava(self, tmp: str, linhas: list[dict[str, str]]) -> Path:
        caminho = Path(tmp) / "labels.csv"
        loja = labels_module.LabelStore(caminho)
        for campos in linhas:
            base = {"filename": "x.png", "fen": "8/8/8/8/8/8/8/8 w - - 0 1"}
            base.update(campos)
            loja.append(labels_module.DatasetEntry(**base))  # type: ignore[arg-type]
        return caminho

    def test_devolve_a_tripla_como_esta_no_csv(self) -> None:
        """Sem conversão de base: aqui a tripla é chave de igualdade, não índice de tela."""
        with tempfile.TemporaryDirectory() as tmp:
            caminho = self._grava(
                tmp, [{"filename": "a.png", "source_pdf": "livro.pdf", "source_page": "41", "source_diagram": "1"}]
            )
            self.assertEqual(labels_module.label_origins(caminho), {"a.png": ("livro.pdf", "41", "1")})

    def test_linha_sem_procedencia_sai_com_a_tripla_vazia(self) -> None:
        """84,1% do acervo. Quem agrupa descarta; inventar procedência seria pior."""
        with tempfile.TemporaryDirectory() as tmp:
            caminho = self._grava(tmp, [{"filename": "a.png"}])
            self.assertEqual(labels_module.label_origins(caminho), {"a.png": ("", "", "")})

    def test_passa_pela_porta_unica_do_labels_csv(self) -> None:
        """S-51: nada lê o `labels.csv` fora do `LabelStore`, nem o agrupamento novo."""
        origem = inspect.getsource(labels_module.label_origins)
        self.assertIn("LabelStore", origem)


class SavedDiagramsByPageTests(unittest.TestCase):
    """O índice que pinta de verde, no visualizador, o que já foi salvo (S-71)."""

    def _entrada(self, **campos: str) -> labels_module.DatasetEntry:
        base = {
            "filename": "board.png",
            "fen": "8/8/8/8/8/8/8/8 w - - 0 1",
            "source_pdf": "livro.pdf",
            "source_page": "17",
            "source_diagram": "3",
        }
        base.update(campos)
        return labels_module.DatasetEntry(**base)  # type: ignore[arg-type]

    def test_converte_as_duas_contagens_para_base_0(self) -> None:
        """O CSV grava base 1 (a página que o usuário vê); a interface conta de 0."""
        achado = labels_module.saved_diagrams_by_page([self._entrada()], "livro.pdf")
        self.assertEqual(achado, {16: {2}})

    def test_junta_os_diagramas_da_mesma_pagina(self) -> None:
        entradas = [self._entrada(source_diagram="1"), self._entrada(source_diagram="4")]
        self.assertEqual(labels_module.saved_diagrams_by_page(entradas, "livro.pdf"), {16: {0, 3}})

    def test_ignora_amostra_de_outro_livro(self) -> None:
        entradas = [self._entrada(), self._entrada(source_pdf="outro.pdf")]
        self.assertEqual(labels_module.saved_diagrams_by_page(entradas, "livro.pdf"), {16: {2}})

    def test_linha_sem_procedencia_e_ignorada_e_nao_e_caso_raro(self) -> None:
        """98,6% do acervo é anterior à S-19 e tem `source_page` vazio."""
        entradas = [self._entrada(source_page="", source_diagram="")]
        self.assertEqual(labels_module.saved_diagrams_by_page(entradas, "livro.pdf"), {})

    def test_o_20_ponto_0_herdado_do_pandas_ainda_e_lido(self) -> None:
        """A S-58 corrigiu a escrita; arquivos antigos ainda têm o formato float gravado."""
        entradas = [self._entrada(source_page="20.0", source_diagram="2.0")]
        self.assertEqual(labels_module.saved_diagrams_by_page(entradas, "livro.pdf"), {19: {1}})

    def test_livro_sem_nome_nao_casa_com_as_linhas_sem_procedencia(self) -> None:
        entradas = [self._entrada(source_pdf="")]
        self.assertEqual(labels_module.saved_diagrams_by_page(entradas, ""), {})

    # ------------------------------------------------ o mesmo índice, sem ler o arquivo (S-116)

    def test_marcar_a_amostra_gravada_da_o_mesmo_indice_que_reler_o_csv(self) -> None:
        """**O que trava o corte 2 da S-116.** As duas funções produzem o mesmo índice, e por
        isso a janela pode marcar o que gravou em vez de redescobri-lo em 30,9 ms de leitura.

        Se um dia elas divergirem, o sintoma seria uma caixa que não fica verde até o livro ser
        reaberto -- o defeito da S-71 de volta, e por um caminho que ninguém procuraria.
        """
        entradas = [self._entrada(source_page="17", source_diagram="3")]
        relido = labels_module.saved_diagrams_by_page(entradas, "livro.pdf")

        marcado: dict[int, set[int]] = {}
        gravada = labels_module.SavedSample(source_pdf="livro.pdf", page_index=16, diagram_index=2)
        self.assertTrue(labels_module.note_saved_diagram(marcado, gravada, source_pdf="livro.pdf"))

        self.assertEqual(marcado, relido)

    def test_marcar_acumula_na_pagina_que_ja_tinha(self) -> None:
        indice: dict[int, set[int]] = {16: {0}}
        gravada = labels_module.SavedSample("livro.pdf", 16, 2)
        labels_module.note_saved_diagram(indice, gravada, source_pdf="livro.pdf")
        self.assertEqual(indice, {16: {0, 2}})

    def test_amostra_de_outro_livro_nao_entra_no_indice(self) -> None:
        """O índice é do livro aberto, e a defesa mora aqui e não em quem chama."""
        indice: dict[int, set[int]] = {}
        gravada = labels_module.SavedSample("outro.pdf", 16, 2)
        self.assertFalse(labels_module.note_saved_diagram(indice, gravada, source_pdf="livro.pdf"))
        self.assertEqual(indice, {})

    def test_indice_negativo_nao_entra(self) -> None:
        """Mesma recusa de `saved_diagrams_by_page`: página 0 no CSV vira -1 aqui."""
        indice: dict[int, set[int]] = {}
        self.assertFalse(
            labels_module.note_saved_diagram(
                indice, labels_module.SavedSample("livro.pdf", -1, 2), source_pdf="livro.pdf"
            )
        )
        self.assertEqual(indice, {})


if __name__ == "__main__":
    unittest.main()
