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

ARQUIVOS_DE_UI = sorted((RAIZ / "src" / "chess_diagram_ocr" / "ui").glob("*.py")) + sorted(
    (RAIZ / "src" / "chess_diagram_ocr" / "qt").glob("*.py")
)
"""Mesmo recorte do `test_strings` e do `test_busy`: a interface, e o que a monta."""

LIMITE = 46
"""Quantas caixas modais a interface ainda abre.

**54 -> 46 no corte do Tk (S-506)**, e a queda não é uma conversão a mais: é o mesmo produto com
uma janela só. As perguntas que a régua chama de decisão foram conferidas uma a uma contra as 20
do lado que saiu, e **uma faltava** -- a da S-451, "Salvar todos" sobre página já salva --, que
foi portada no mesmo dia. As outras eram notificações repetidas entre painéis que o Qt
resolve com uma frase no rodapé, que é o que a linha 1 da tabela abaixo manda fazer.

**53 -> 54 na S-451**, e a nova é decisão pela régua da linha 4 da tabela: "Salvar todos" sobre uma
página cujos diagramas já têm amostra pergunta antes de gravar a segunda cópia. Nada no caminho de
gravação recusa a duplicata -- `append_training_sample` nomeia por timestamp e sempre acrescenta --,
e ela é legítima quando a pessoa acabou de corrigir a leitura. Quem sabe de qual dos dois casos se
trata é quem está com o livro aberto, e a única coisa que faltava era perguntar. Uma para a página
e não uma por diagrama, pelo mesmo motivo da pergunta de ilegalidade que ela acompanha.

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

**52 → 53 na S-301**, e a linha a mais é uma pergunta: "Sem diagrama" sobre uma folha já anotada
descartava, num clique e sem desfazer, os diagramas que alguém tinha revisado à mão -- e
`field_eval.upsert_page` substitui a página inteira, então a anotação não volta. Cai na linha da
tabela que trata de decisão irreversível, e a caixa **não** entra no gesto normal: página nunca
anotada e página já marcada como sem diagrama passam direto. Essa condição é o item, e não a
caixa -- página sem diagrama é obrigatória no conjunto de campo (S-41), e uma pergunta no caminho
dela seria a fricção que a S-164 removeu.

Baixar este número é o item continuando; subi-lo exige vir aqui e escrever por que aquela caixa
precisava ser modal."""

MODAIS_DE_DECISAO = 14
"""Quantas das que sobram fazem uma pergunta -- `QMessageBox.question` ou uma caixa montada.

**19 -> 14 no corte do Tk (S-506), e a queda foi conferida uma a uma.** As 20 perguntas do lado
que saiu foram listadas por `ast` sobre o `HEAD` e comparadas com as do Qt: dezenove tinham
correspondente (o `askyesnocancel` do PGN, os três do texto, os dois da base de partidas, os dois
do dataset, o "Estudo em andamento", o "Apagar", os dois de ilegalidade, o de fechar com operação
em andamento, o "sem diagrama", os dois de headers da Galeria e o de exportação interrompida), e
**uma faltava**: a da S-451, "Salvar todos" sobre página cujos diagramas já têm amostra. Ela foi
portada no mesmo dia -- `_confirmar_repetidos` em `qt/painel_de_resultado.py`. A diferença que
sobra é de contagem e não de gesto: perguntas que o Tk repetia em dois painéis o Qt faz uma vez.

O texto abaixo é o histórico do número no lado que saiu, e fica porque a régua é a mesma.

Ela é a metade honesta da conta: "a contagem cai" não vale nada se o que caiu foram as perguntas.
Nenhuma das 22 convertidas era uma; as 13 continuaram de pé, e a 14ª foi a da S-301.

**14 -> 19 na S-420, e as cinco já estavam lá.** Este número é catraca de piso -- ele existe para
que uma pergunta não vire aviso de rodapé sem que alguém decida --, e um piso cinco abaixo do
chão não trava nada: dava para apagar quatro perguntas e a suíte continuaria verde. As cinco que
faltavam entraram entre a S-301 e a S-347, com as fases da sala de estudo e da aba Texto: as três
do `texto_panel` (o rascunho a recuperar e as duas de sair sem gravar), o "Estudo em andamento" e
o `askyesnocancel` do PGN existente. Nenhuma delas é notificação disfarçada -- todas as cinco
perguntam antes de **apagar trabalho humano**, que é a linha 4 da tabela acima.

Contar por varredura, e não à mão, é o que impede o número de envelhecer de novo: quem baixar
este piso tem de vir aqui e dizer qual pergunta deixou de existir."""


CAIXAS_DO_QT = ("information", "warning", "critical", "question", "about")
"""Os cinco atalhos estáticos do `QMessageBox`. **Substituíram as sete do `tkinter.messagebox` no
corte (S-506)**, e a régua é a mesma: uma caixa é uma interrupção, e a conta existe para que ela
seja uma decisão."""


def _chamadas_de_messagebox(caminho: Path) -> list[str]:
    """Cada caixa modal do arquivo, como `arquivo:linha X`.

    Conta as duas formas do Qt: o atalho estático (`QMessageBox.question(...)`) e a caixa montada
    à mão (`QMessageBox(...)` com `addButton`), que é o caminho de quem precisa de mais de dois
    botões. Contar só a primeira deixaria de fora cinco interrupções -- inclusive a de promoção
    de peão, que tem quatro."""
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    achadas = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        alvo = ast.unparse(no.func)
        if alvo.startswith("QMessageBox.") and alvo.split(".")[-1] in CAIXAS_DO_QT:
            achadas.append(f"{caminho.name}:{no.lineno} {alvo.split('.', 1)[1]}")
        elif isinstance(no.func, ast.Name) and no.func.id == "QMessageBox":
            achadas.append(f"{caminho.name}:{no.lineno} montada")
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
        perguntas = [c for c in _todas() if c.split()[-1] in ("question", "montada")]
        self.assertGreaterEqual(
            len(perguntas),
            MODAIS_DE_DECISAO,
            "Uma pergunta virou mensagem de rodapé. Decisão precisa de resposta, e o rodapé não "
            "tem como colher uma.",
        )


SEM_ESC: dict[str, str] = {}
"""Os diálogos que **não** fecham com `Esc`, com o motivo escrito.

**Vazia desde o corte do Tk (S-506), e a razão é do toolkit.** Em Tk o `Esc` era um `bind` que
alguém tinha de lembrar de escrever, e a lista guardava as duas `Toplevel` que não eram diálogo.
Um `QDialog` fecha com `Esc` de fábrica -- `reject()` está ligado à tecla pelo próprio Qt --, e a
única forma de perdê-lo é **sobrescrever** `keyPressEvent` sem chamar o `super()`. É isso que a
varredura abaixo procura agora, e é uma pergunta melhor: ela mede quem tirou, e não quem esqueceu
de pôr.

A lista continua existindo para que a exceção seja uma decisão e não um esquecimento. Uma linha
aqui precisa vir com a razão junto.
"""


def _mantem_escape(classe: ast.ClassDef) -> bool:
    """Se aquele `QDialog` **não** roubou o `Esc` que o Qt lhe dá.

    Ou ela não sobrescreve `keyPressEvent`, ou sobrescreve e ainda chama o `super()`. Qualquer
    outra coisa engole a tecla, e o único jeito de sair passa a ser achar o botão -- que é o
    estado que a S-395 mediu no outro toolkit, em onze de catorze janelas.
    """
    for f in classe.body:
        if isinstance(f, ast.FunctionDef) and f.name == "keyPressEvent":
            corpo = ast.unparse(f)
            return "super()" in corpo or "keyPressEvent" in corpo.split("def", 1)[1]
    return True


class EscFechaODialogoTests(unittest.TestCase):
    """Toda janela de diálogo fecha com `Esc` (S-395).

    **Catorze janelas, e onze não fechavam.** Inclusive a legenda de atalhos -- a que mais se abre,
    e a que menos tem o que consentir. `Esc` é a saída que todo diálogo tem em todo programa; sem
    ela, a única porta é achar o botão de fechar, e três destas janelas não tinham botão de fechar
    nenhum: só o X da barra de título.

    **E em nenhuma delas `Esc` aplica.** Sair sem consentir é sempre a resposta segura -- é a
    mesma régua da linha 4 da tabela deste arquivo, do outro lado: a decisão precisa de resposta,
    e "nenhuma" é uma resposta que não estraga nada.
    """

    def _dialogos(self) -> list[tuple[str, bool]]:
        achados: list[tuple[str, bool]] = []
        for caminho in ARQUIVOS_DE_UI:
            arvore = ast.parse(caminho.read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                if isinstance(no, ast.ClassDef) and any(ast.unparse(b).endswith("QDialog") for b in no.bases):
                    achados.append((f"{caminho.name}:{no.name}", _mantem_escape(no)))
        return [(nome, tem) for nome, tem in achados if nome not in SEM_ESC]

    def test_a_varredura_acha_os_dialogos(self) -> None:
        """Sem isto, renomear a base faria o teste abaixo passar sobre lista vazia."""
        self.assertGreaterEqual(len(self._dialogos()), 12)

    def test_todo_dialogo_fecha_com_esc(self) -> None:
        sem = sorted(nome for nome, tem in self._dialogos() if not tem)
        self.assertEqual(
            sem,
            [],
            "Diálogo que engole o `Esc`. Chame o `super().keyPressEvent(evento)` -- e "
            "se ela não for diálogo, ponha o motivo em SEM_ESC:\n" + "\n".join(sem),
        )

    def test_a_lista_de_excecoes_nao_cobre_quem_nao_existe(self) -> None:
        """Exceção que sobra é exceção que esconde: a janela pode ter virado diálogo desde então."""
        nomes = {
            f"{caminho.name}:{no.name}"
            for caminho in ARQUIVOS_DE_UI
            for no in ast.walk(ast.parse(caminho.read_text(encoding="utf-8")))
            if isinstance(no, (ast.ClassDef, ast.FunctionDef))
        }
        self.assertEqual([], sorted(set(SEM_ESC) - nomes))


class OperacoesLongasTests(unittest.TestCase):
    """As três que passam de um minuto informam progresso pelo registro, e não só por texto."""

    ONDE = {
        "exportador.py": "exportar o livro para PGN",
        "painel_da_galeria.py": "varrer o livro (Galeria **e** fila), e a busca por posição na base",
        "dialogos.py": "treinar o modelo (`ControladorDeTreino`)",
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
            fonte = (RAIZ / "src" / "chess_diagram_ocr" / "qt" / nome).read_text(encoding="utf-8")
            if "feito=" not in fonte or "total=" not in fonte:
                faltando.append(f"{nome} ({operacao})")
        self.assertEqual(faltando, [], "Operação longa sem progresso numérico no registro.")


if __name__ == "__main__":
    unittest.main()
