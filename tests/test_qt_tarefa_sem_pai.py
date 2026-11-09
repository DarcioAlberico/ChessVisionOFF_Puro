"""Nenhuma `Tarefa` tem pai, e a janela espera todas ao fechar (S-826).

**O modo de falha é o de `qt/trabalho.manter_viva`**: o Qt destrói os filhos junto com o pai, e o
destrutor de `QThread` aborta o processo se a thread ainda roda -- sem traceback, porque a queda é
no C++. A janela seguia a regra desde a F9-C2; dezesseis tarefas dos painéis (seis só na aba Texto)
nasciam com `parent=self`, e o `closeEvent` esperava a da janela e não a delas. Ler uma folha na
aba Texto e fechar a janela bastava para o processo morrer na saída.

Três coisas aqui: o processo que sai com 0 (num subprocesso, porque o que se mede é o processo); o
slot que não toca um dono apagado; e a guarda que não deixa o `parent=` voltar.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from ambiente_de_teste import pasta_temporaria
from qt_app import MOTIVO, TEM_PYQT, aplicacao

RAIZ = Path(__file__).resolve().parents[1]
PACOTE = RAIZ / "src" / "chess_diagram_ocr"

LER_E_FECHAR = r'''
import sys, time
from pathlib import Path

import fitz
from PyQt6 import sip
from PyQt6.QtWidgets import QApplication

pasta = Path(PASTA)
livro = pasta / "livro.pdf"
doc = fitz.open()
doc.new_page(width=300, height=400)
doc.save(livro)
doc.close()

app = QApplication([])
from chess_diagram_ocr.qt import painel_de_texto, trabalho
from chess_diagram_ocr.qt.janela import JanelaPrincipal
from chess_diagram_ocr.text.documento import PaginaLida


class Servico:
    device = None
    device_label = ""
    caption_reader = None

    def invalidate_model(self, caminho=None):
        pass

    def model_session(self, caminho):
        return None


def ler_devagar(caminho, indice, **_):
    time.sleep(2.0)  # a leitura da folha pelo motor, que leva segundos
    return PaginaLida(documento=str(caminho), pagina=indice, colunas=())


painel_de_texto._ler = ler_devagar
painel_de_texto._renderizar = lambda *_a, **_k: None
janela = JanelaPrincipal(
    motor=None, servico=Servico(), csv_de_rotulos=pasta / "labels.csv", pasta_de_estudos=pasta,
    pasta_da_galeria=pasta, caminho_do_cache=pasta / "posicoes.sqlite", caminho_do_estado=pasta / "janela.json",
)
janela.texto.definir_livro(livro, paginas=1)
janela.texto.ler()
time.sleep(0.3)
if not trabalho.tarefas_rodando():
    sys.exit("a leitura não começou: o teste não mediu nada")
janela.close()
print("a janela fechou; destruindo", file=sys.stderr, flush=True)
sip.delete(janela)  # o que a saída do programa faz com a janela, e com os filhos dela
rodando = trabalho.tarefas_rodando()
if rodando:
    print("a janela fechou sem esperar:", [t.nome for t in rodando], file=sys.stderr)
    sys.exit(3)
'''


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class FecharComLeituraTests(unittest.TestCase):
    def test_ler_uma_folha_e_fechar_a_janela_sai_com_zero(self) -> None:
        """O critério de aceite da S-826: a leitura da aba Texto em curso, a janela fecha e é
        destruída, e o processo sai com 0 -- sem a tarefa abortar com o painel, e sem sobrar."""
        from subprocesso import rodar_python

        pasta = pasta_temporaria(self)
        feito = rodar_python(LER_E_FECHAR.replace("PASTA", repr(str(pasta))), check=False, timeout=180)
        self.assertEqual(0, feito.returncode, f"o processo caiu ({feito.returncode:#x}):\n{feito.stderr[-3000:]}")


@unittest.skipUnless(TEM_PYQT, MOTIVO)
class SlotSeVivoTests(unittest.TestCase):
    def test_o_slot_so_roda_enquanto_o_dono_existe(self) -> None:
        """A `Tarefa` sem pai sobrevive ao painel; a resposta dela não pode tocá-lo depois."""
        from PyQt6 import sip
        from PyQt6.QtCore import QObject

        from chess_diagram_ocr.qt.trabalho import slot_se_vivo

        aplicacao()
        dono = QObject()
        chegou: list[object] = []
        slot = slot_se_vivo(dono, lambda *valores: chegou.append(valores))
        slot(1, 2)
        sip.delete(dono)
        slot(3)  # não levanta, e não chega
        self.assertEqual([(1, 2)], chegou)


JUSTIFICADAS: dict[str, str] = {}
"""`arquivo:linha` -> por que esta `Tarefa` foge da regra. **Vazia, e o piso é zero**: a regra não
tem exceção conhecida, e uma entrada nova tem de dizer aqui por que a sua não aborta o processo."""


def _nomes_de_tarefa(arvore: ast.AST) -> set[str]:
    """`Tarefa` e os apelidos dela no arquivo (`from ... import Tarefa as T`)."""
    nomes = {"Tarefa"}
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom):
            nomes |= {nome.asname for nome in no.names if nome.name == "Tarefa" and nome.asname}
    return nomes


def _termo(no: ast.expr) -> str:
    return no.attr if isinstance(no, ast.Attribute) else no.id if isinstance(no, ast.Name) else ""


def tarefas_fora_da_regra(fonte: str, rotulo: str) -> tuple[int, list[str]]:
    """Quantas `Tarefa(...)` o código constrói, e quais fogem da regra: com pai (`parent=` ou um
    segundo posicional) ou fora de um `manter_viva(...)`, que é quem a segura até acabar."""
    arvore = ast.parse(fonte)
    nomes = _nomes_de_tarefa(arvore)
    seguras = {
        id(no.args[0])
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call) and _termo(no.func) == "manter_viva" and no.args
    }
    achadas, fora = 0, []
    for no in ast.walk(arvore):
        if not (isinstance(no, ast.Call) and _termo(no.func) in nomes):
            continue
        achadas += 1
        com_pai = len(no.args) > 1 or any(chave.arg == "parent" for chave in no.keywords)
        if com_pai or id(no) not in seguras:
            fora.append(f"{rotulo}:{no.lineno}" + (" com pai" if com_pai else " sem manter_viva"))
    return achadas, fora


class GuardaDeTarefaComPaiTests(unittest.TestCase):
    def test_nenhuma_tarefa_do_programa_tem_pai(self) -> None:
        achadas, fora = 0, []
        for arquivo in sorted(PACOTE.rglob("*.py")):
            if arquivo.name == "trabalho.py":
                continue  # onde a classe mora; as dela são `manter_viva` por construção
            rotulo = arquivo.relative_to(PACOTE).as_posix()
            quantas, desta = tarefas_fora_da_regra(arquivo.read_text(encoding="utf-8"), rotulo)
            achadas += quantas
            fora += [achado for achado in desta if achado.rsplit(" ", 2)[0] not in JUSTIFICADAS]
        self.assertGreaterEqual(achadas, 20, "a varredura não acha as tarefas que existem: ficou vácua")
        self.assertEqual([], fora, "`Tarefa` com pai aborta o processo ao fechar: ver `qt/trabalho.manter_viva`")
        self.assertEqual({}, JUSTIFICADAS, "o piso é zero: uma exceção nova sobe o piso, e diz por quê")

    def test_a_guarda_acha_o_que_procura(self) -> None:
        """Prova de que ela pega cada forma: `parent=`, pai posicional, apelido, atributo e solta."""
        fonte = (
            "from chess_diagram_ocr.qt.trabalho import Tarefa as T\n"
            "a = Tarefa(f, parent=self)\n"
            "b = manter_viva(trabalho.Tarefa(f, self))\n"
            "c = T(f)\n"
            "d = manter_viva(Tarefa(f, nome='x'))\n"
        )
        achadas, fora = tarefas_fora_da_regra(fonte, "x.py")
        self.assertEqual(4, achadas)
        self.assertEqual(["x.py:2 com pai", "x.py:3 com pai", "x.py:4 sem manter_viva"], sorted(fora))


if __name__ == "__main__":
    unittest.main()
