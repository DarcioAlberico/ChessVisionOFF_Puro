"""O retorno que devia ser ambiente era modal, e a conta é a catraca (S-164).

**O número que abriu o item eram 66 chamadas de `messagebox`** em `ui/` mais o `app_tkinter.py`,
contra três `ttk.Progressbar` — nenhuma delas nas três operações que passam de um minuto. O
diagnóstico da spec é que a interface só tinha um jeito de dizer qualquer coisa, e esse jeito
interrompia: sem rodapé com severidade (S-163), "salvo" e "falhou" tinham a mesma aparência, e a
única forma de destacar era abrir uma caixa que pede clique.

**A avaliação disse 76, e o número certo é 66.** O 76 saiu de `grep -c messagebox`, que conta
também `default=messagebox.NO` e `icon=messagebox.WARNING` — constantes passadas para outra
chamada, e não caixas. A contagem daqui é por AST: `messagebox.X(...)` como **chamada**. A
correção não muda nenhuma conclusão do item (66 caixas contra 3 barras de progresso é a mesma
frase), e fica registrada porque um número citado em documento que ninguém consegue reproduzir é
o mecanismo da S-135.

**O critério da conversão, e ele é a razão de este teste existir por contagem e não por lista.**

| o que é | onde vai | por quê |
|---|---|---|
| confirmação de sucesso | rodapé | ninguém precisa autorizar o que já aconteceu |
| pré-condição de uma frase ("abra um PDF antes") | rodapé | é um passo que falta, não uma escolha |
| "já existe X em execução" | rodapé | a zona de operação ao lado está mostrando exatamente isso |
| decisão (sobrescrever? salvar posição ilegal? apagar?) | **modal** | ela precisa de resposta |
| instrução de várias linhas (onde pôr a base de partidas) | **modal** | o rodapé é uma linha |
| erro | **modal** | interrompe um gesto que a pessoa acabou de fazer |

**Erro continua modal, e isso é escolha declarada.** O rodapé sabe mostrar erro e não o expira
(ver `EXPIRACAO_MS`), então a mecânica existe. O que decidiu contra converter os 23 `showerror`
é o custo assimétrico: uma falha de gravação que ninguém veja é trabalho humano perdido em
silêncio, e a S-76 é o registro do que isso custa neste projeto. Fica escrito aqui para o próximo
item não ter de adivinhar se foi esquecimento.

A contagem é catraca como a de `app_tkinter.py` em `test_packaging.py`: ela não impede subir,
impede subir **sem decidir**.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

ARQUIVOS_DE_UI = sorted((RAIZ / "src" / "chess_diagram_ocr" / "ui").glob("*.py")) + [RAIZ / "app_tkinter.py"]
"""Mesmo recorte do `test_strings` e do `test_busy`: a interface, e o que a monta."""

LIMITE = 52
"""Quantas chamadas de `messagebox` a interface ainda faz.

**51 -> 52 na S-289**, e a nova é um `showerror` de falha ao **gravar** o estudo exportado --
linha 6 da tabela: erro interrompe um gesto que a pessoa acabou de fazer, e ela acabou de escolher o
arquivo. É a mesma caixa que `save_pgn` já tinha ao lado, pela mesma razão.

**49 -> 51 nas S-270 e S-275**, e as duas são decisão pela régua da linha 4 da tabela: elas
perguntam antes de **apagar análise humana**, que é a regra 7 da SPEC_ESTUDO.

`_confirmar_abandono` só aparece para o estudo **avulso** -- o de uma FEN digitada à mão, que não
está atado a diagrama nenhum e por isso não tem para onde ir quando se troca de posição. Estudo com
âncora no livro não pergunta nada: ele fica guardado na sala e volta ao próximo clique naquele
diagrama, que é exatamente o que a S-270 veio entregar. `_confirmar_apagar` só aparece quando há
mais de um lance ou anotação a perder -- apagar um lance solto é o desfazer de um clique errado, e
perguntar ali seria atrito.

Ou seja: as duas caixas novas existem para que a interface **pare** de fazer em silêncio o que
fazia antes -- `_set_board_state` descartava a árvore inteira sem uma palavra.

**48 -> 49 na S-255**, e a nova é a pergunta de recuperação do rascunho. Ela é decisão pela
régua da tabela acima: o que está na tela muda conforme a resposta, e a resposta não pode ser
adivinhada -- um rascunho de dez minutos atrás é o trabalho que a pessoa acabou de perder, e
um de três semanas é lixo que ela já esqueceu. Por isso a pergunta **diz a data**, e por isso
recusar não apaga nada.

**66 → 44 na S-164**, e as 22 que saíram estão nas linhas 1 a 3 da tabela do docstring: dois fins
de operação longa (a exportação de 402 páginas e o treino de horas), nove pré-condições, três "já
está rodando", quatro confirmações de sucesso que **repetiam a frase que o rodapé já mostrava**, e
o "nenhum diagrama nesta página" -- que era um clique obrigatório no caso mais comum do programa,
porque livro de exercícios cai em prosa a cada duas ou três páginas.

Das 44 que ficaram, 23 são `showerror`, 13 são pergunta e 8 são instrução ou resposta de várias
linhas.

**44 → 45 na S-161**, e a linha a mais é a catraca funcionando como devia: o "Sobre" do menu Ajuda.
Ela é a exceção que a tabela acima não cobria -- uma caixa que a pessoa **pediu**, por um item de
menu, não interrompe nada: ela é a resposta a um clique, e some no clique seguinte. O que a S-164
tirou foi caixa que aparecia sem ninguém pedir.

**45 → 48 na S-238**, e as três são o editor de texto ganhando arquivo próprio. Duas são erro --
o `.cvtxt` que não gravou e o que não abriu --, e caem na última linha da tabela pelo motivo que
ela declara: falha de gravação que ninguém vê é trabalho humano perdido em silêncio, e uma sessão
de correção é a coisa mais cara desta aba. A terceira é pergunta: abrir outro arquivo com o texto
editado descarta o que está na tela, e descartar é decisão -- é a mesma caixa que `ler` já faz
antes de reler a folha, e pela mesma razão.

Baixar este número é o item continuando; subi-lo exige vir aqui e escrever por que aquela caixa
precisava ser modal."""

MODAIS_DE_DECISAO = 13
"""Quantas das que sobram fazem uma pergunta -- `askyesno`, `askokcancel`, `askyesnocancel`.

Ela é a metade honesta da conta: "a contagem cai" não vale nada se o que caiu foram as perguntas.
Nenhuma das 22 convertidas era uma; as 13 continuam de pé, e este número é o que trava isso."""


def _chamadas_de_messagebox(caminho: Path) -> list[str]:
    """Cada `messagebox.X(...)` do arquivo, como `arquivo:linha X`."""
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    achadas = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        alvo = ast.unparse(no.func)
        if alvo.startswith("messagebox."):
            achadas.append(f"{caminho.name}:{no.lineno} {alvo.split('.', 1)[1]}")
    return achadas


def _todas() -> list[str]:
    return [chamada for caminho in ARQUIVOS_DE_UI for chamada in _chamadas_de_messagebox(caminho)]


class ContagemDeModaisTests(unittest.TestCase):
    def test_a_interface_nao_volta_a_interromper_mais_do_que_hoje(self) -> None:
        atual = _todas()
        self.assertLessEqual(
            len(atual),
            LIMITE,
            f"As chamadas de `messagebox` subiram de {LIMITE} para {len(atual)}. Uma caixa modal "
            "nova ou é decisão (e o motivo entra no docstring deste arquivo), ou é mensagem de "
            "rodapé -- ver `ui/rodape.py`.",
        )

    def test_a_catraca_nao_esta_defasada_para_baixo(self) -> None:
        """Catraca que não aperta não é catraca: converter mais dez sem baixar o corte devolve
        a folga, e a próxima caixa entra sem ninguém ver."""
        atual = _todas()
        self.assertGreater(len(atual) + 6, LIMITE, f"São {len(atual)} chamadas e o corte ainda é {LIMITE}.")

    def test_o_que_sobrou_de_pergunta_continua_de_pe(self) -> None:
        """O que caiu foram notificações, e não decisões -- é isto que separa as duas coisas."""
        perguntas = [c for c in _todas() if c.split()[-1].startswith("ask")]
        self.assertGreaterEqual(
            len(perguntas),
            MODAIS_DE_DECISAO,
            "Uma pergunta virou mensagem de rodapé. Decisão precisa de resposta, e o rodapé não "
            "tem como colher uma.",
        )


class OperacoesLongasTests(unittest.TestCase):
    """As três que passam de um minuto informam progresso pelo registro, e não só por texto."""

    ONDE = {
        "export_controller.py": "exportar o livro para PGN",
        "gallery_panel.py": "varrer o livro (Galeria **e** fila), e a busca por posição na base",
        "training_dialog.py": "treinar o modelo",
    }
    """Três, e não quatro: o `review_panel.py` saiu na S-119, e não por ter perdido o número.

    Ele tinha passada própria pelo mesmo PDF -- 299 s ao lado dos 338 s da Galeria --, e agora
    a fila é montada da varredura de lá. Quem registra a operação longa e publica `feito=` é
    quem tem a thread, que passou a ser um só; o painel de revisão mostra a página na sua
    barra de texto e não abre um segundo registro para a mesma passada."""

    def test_cada_operacao_longa_publica_o_numero_e_nao_so_a_frase(self) -> None:
        """`token.update(..., feito=, total=)` é o que faz a barra do rodapé ser determinada.

        Sem o número, o `detail` continuaria dizendo "página 120 de 402" e a barra continuaria
        andando sem fim -- que era o estado anterior, com a informação existindo e não chegando.
        """
        faltando = []
        for nome, operacao in self.ONDE.items():
            fonte = (RAIZ / "src" / "chess_diagram_ocr" / "ui" / nome).read_text(encoding="utf-8")
            if "feito=" not in fonte or "total=" not in fonte:
                faltando.append(f"{nome} ({operacao})")
        self.assertEqual(faltando, [], "Operação longa sem progresso numérico no registro.")


if __name__ == "__main__":
    unittest.main()
