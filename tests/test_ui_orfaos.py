"""De cada decisão pura de `ui/`, quem a chama? (S-511)

**A conta que faltava.** O catálogo pergunta se uma ação tem *dono* e se o dono é *chamável* --
`lambda: None` passa nas duas. Nada perguntava se um módulo puro de `ui/` ainda tem **importador**,
e módulo órfão não quebra teste nenhum: o teste dele continua verde medindo a decisão sozinha.

Foi assim que sete decisões ficaram sem chamador no corte do Tk e só voltaram um mês depois
(`adda88f`). As S-507 a S-510 são a oitava à décima primeira, e as quatro moram no mesmo arquivo:
`ui/desenho_do_tabuleiro.py`, que tinha **doze apelidos de cor** existindo para um `tk.Canvas` que
já não existe. A instância muda; o mecanismo não.

**O que esta guarda é e o que ela não é.** Ela não é "conserte os órfãos". É tornar a pergunta
fazível e travar o número. `desenho_do_tabuleiro.py` -- o módulo que este item triou -- não pode
ter nenhum, salvo exceção com motivo escrito; o resto do pacote entra numa catraca que **desce
quando alguém tria um e não sobe**.

**Por que `ast` e não `grep`.** Um nome citado num docstring conta como uso para o `grep`, e é o
caso mais comum de todos neste projeto -- os módulos se descrevem uns aos outros em prosa. A
varredura por identificador conta só o que o código **usa**.

**O que a guarda mede, e o que ela deliberadamente não mede.** Ela pergunta se o **produto**
(`src/`) chama o nome, e não se algum teste o toca. Medido em 2026-09-01, a diferença é grande:
dos 125 nomes que a busca de texto não achava em `src/`, 48 eram tocados por algum teste e 77 não
eram tocados por nada. Um nome que só o próprio teste usa continua sendo uma decisão sem cliente --
é exatamente o estado que deixou as sete passarem despercebidas.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1] / "src" / "chess_diagram_ocr"
UI = RAIZ / "ui"

E_O_TIPO = (
    "é o tipo dos valores que o módulo devolve ou recebe: o cliente lê os atributos e nunca nomeia o "
    "tipo, e um `import` só para anotar seria o chamador escrito para a guarda ficar verde"
)
INSTRUMENTO = (
    "instrumento das guardas: existe para o teste afirmar o que o produto faz, e um chamador no "
    "produto seria o produto medindo a si mesmo"
)
TABELA_PERCORRIDA = (
    "a tabela declarada que a guarda percorre inteira; o produto a lê pelas funções ao lado, e é o "
    "teste que a compara com o que foi montado"
)

SEM_CHAMADOR: dict[str, str] = {
    "estudo_lista.NIVEL_MAXIMO_DE_RECUO": (
        "quem o aplica é o próprio `Trecho.recuo`, no mesmo módulo, e o painel usa o resultado. "
        "Ele tinha chamador até a S-514, quando o recuo saiu do `<span>` e foi para o bloco: o "
        "desenho passou a ler `trecho.recuo`, que já vem saturado. Chamá-lo de fora agora seria "
        "repetir a saturação que a propriedade faz -- um chamador escrito para a guarda ficar "
        "verde, que é o `lambda: None` ao contrário."
    ),
    "desenho_do_tabuleiro.LARGURA_DO_CIRCULO": (
        "a casa marcada do padrão `[%csl]` ainda não é oferecida pela sala -- `_soltar_seta` "
        "recusa a seta de comprimento zero, que é o gesto que a marcaria. A espessura do anel "
        "fica declarada para quando o gesto existir, e não como número solto no widget."
    ),
    # --- os tipos: `ATALHOS` é uma tupla de `Atalho`, `geometria_de_texto` devolve `Geometria`...
    "atalhos.Atalho": E_O_TIPO,
    "atalhos.DonoDeAcoes": E_O_TIPO + " -- e é um `Protocol`: quem o implementa não o nomeia, por definição",
    "board_model.BoardMode": E_O_TIPO,
    "degradacao.Queda": E_O_TIPO,
    "gallery_model.ApplyReport": E_O_TIPO,
    "geometria.Geometria": E_O_TIPO,
    "icones.Arco": E_O_TIPO,
    "icones.Poli": E_O_TIPO,
    "menu.Menu": E_O_TIPO,
    "varredura_de_revisao.ScanRequest": E_O_TIPO,
    # --- os instrumentos: o que a guarda usa para medir, e o produto não
    "tokens.razao_de_contraste": INSTRUMENTO + " (o piso de contraste das S-145/S-159, em `test_board_model` e `test_qt_tema`)",
    "tokens.matiz": INSTRUMENTO + " (a distância de matiz da S-159)",
    "tokens.saturacao": INSTRUMENTO + " (a saturação da S-159)",
    "tokens.distancia_de_matiz": INSTRUMENTO + " (a distância de matiz da S-159)",
    "espaco.vigente": INSTRUMENTO + " -- existe para o teste afirmar o que `ajustar` fixou",
    "abas.contagem_no_rotulo": INSTRUMENTO + " -- existe para o teste ler o que a tela diz, como o docstring dela declara",
    "estudo_lista.texto_de": (
        INSTRUMENTO + " -- é a trava da S-273: `texto_de(trechos(e))` igual ao `StringExporter`, "
        "token a token, cobrada por `test_estudo_lista`"
    ),
    "comandos.primarios_por_grupo": INSTRUMENTO + " -- \"uma ênfase por barra, nunca duas\", cobrada por `test_ui_comandos`",
    # --- as tabelas que a guarda percorre inteiras
    "tokens.NO_CROMO_ESCURO": TABELA_PERCORRIDA,
    "tokens.PAPEIS": TABELA_PERCORRIDA,
    "tokens.SUPERFICIES": TABELA_PERCORRIDA + " (`test_ui_superficies`, a guarda da S-449)",
    "tokens.SUPERFICIES_DE_DOCUMENTO": TABELA_PERCORRIDA,
    "comandos.CATALOGO": TABELA_PERCORRIDA + " -- é a conta do catálogo, em `test_ui_comandos` e `test_qt_janela`",
    "comandos.NAS_BARRAS_DO_PDF": (
        TABELA_PERCORRIDA + " -- religada em `ee1b878`, quando se viu que declarava 16 e o painel "
        "desenhava 11: sem leitor, uma declaração não só perde o chamador, ela deriva"
    ),
    # --- os dois que têm cliente fora de `src/`
    "plataforma.gravar_icone": (
        "ferramenta de build chamada à mão: gera o `.ico` versionado que `packaging/cvoff.spec` "
        "declara (\"Gerado por ui/plataforma.py::gravar_icone()\"). O produto nunca o chama "
        "porque o arquivo já vai pronto."
    ),
    "geometria.fracao_do_documento": (
        "o orçamento da S-232 -- o documento fica com pelo menos 60% da altura --, cobrado por "
        "`test_qt_fita.test_o_documento_fica_com_pelo_menos_sessenta_por_cento_da_altura`. No "
        "produto o orçamento não é lido, é cumprido."
    ),
    # --- o segundo lote (2026-09-02): mais duas tabelas, um instrumento, e o que o porte não trouxe
    "degradacao.QUEDAS": TABELA_PERCORRIDA + " (`test_ui_degradacao`, revivido: morreu no corte com a raiz Tk que abria)",
    "degradacao.avisos_dados": INSTRUMENTO + " -- conta os avisos dados, para o teste afirmar o `uma vez`",
    "icones.ICONES": TABELA_PERCORRIDA + " (`test_ui_icones`, nos dois sentidos com o catálogo de comandos)",
    "texto_declarado.ROTULO_DO_CORPO_MISTO": (
        "o mostrador de corpo da S-292 não foi portado para o Qt (o painel não tem o rótulo); fica "
        "declarado para quando for, como `LARGURA_DO_CIRCULO`"
    ),
    "texto_declarado.ESCAPE_DA_PALETA": (
        "a sequência digitada da S-248 depende de a digitação chegar ao documento, e no editor do "
        "Qt ela ainda não chega -- medido em 2026-09-02: o widget recebe o texto e `documento` não. "
        "Fica declarada para quando chegar (S-521); portá-la antes seria trocar um caractere que "
        "o documento não tem."
    ),
    "texto_declarado.COMANDO_DA_ESCOLHA": (
        "as listas de escolha exclusiva da S-259/S-262 não foram portadas: no Qt alinhamento e "
        "caixa são botões, um por comando, e a tabela nome-do-domínio -> comando fica para as listas"
    ),
    "texto_declarado.ALINHAMENTO": "a chave de `COMANDO_DA_ESCOLHA`, pelo mesmo motivo",
    "atalhos.SOBREPOSICOES_NO_EDITOR": (
        TABELA_PERCORRIDA + " -- o produto a lê por `sobreposicao` e `teclas_cedidas_ao_editor`, e "
        "`test_ui_atalhos` a confere contra `ACOES_PROPRIAS` nos dois sentidos"
    ),
    "atalhos.CEDIDA_PELA_GUARDA": "um dos dois valores que `sobreposicao` devolve; quem os distingue é o teste",
    "atalhos.GANHA_DO_TK": "o outro valor que `sobreposicao` devolve; quem os distingue é o teste",
    # --- a barra da sala (S-527, 2026-09-04): nasceu com a catraca em zero, e respondeu na hora
    #
    # `barra_da_sala.ACOES` **saiu** desta lista na S-528, e não por ter ganhado chamador: a
    # varredura é por **identificador**, e `qt/painel_do_pdf.py` passa `barra_do_pdf.ACOES` para a
    # fila -- o nome `ACOES` passou a existir fora de `ui/barra_da_sala.py`, e a pergunta deixou de
    # ser feita para os dois. É limitação conhecida do detector (ver o cabeçalho: ele conta
    # identificador, não par módulo-nome), e o que continua cobrando a tabela da sala é
    # `tests/test_ui_barra_da_sala.py`, nos dois sentidos com `COMANDOS_DA_ABA` e `ICONES_DA_SALA`.
    "barra_da_sala.SEM_ESTUDO": "um dos três valores que `modo` devolve e `grupos_desligados` consome; quem os distingue é o teste",
    "barra_da_sala.COM_ESTUDO": "o segundo valor de `modo`, pelo mesmo motivo",
    "barra_da_sala.TREINANDO": "o terceiro valor de `modo`, pelo mesmo motivo",
    "barra_da_sala.EXPORTAR_ESTUDO": (
        "o agrupador \"Exportar\": o widget o acha por `Acao.agrupador`, lendo a tabela, e só o teste o "
        "chama pelo nome -- ao contrário de `SEGUIR_OCR`, o outro nome fora do catálogo, que o painel chama"
    ),
    "icones.ICONES_DA_SALA": (
        TABELA_PERCORRIDA + " (`test_ui_barra_da_sala`, nos dois sentidos com `barra_da_sala.ACOES`; "
        "`imagem` a lê por `tracos_de`, no mesmo módulo)"
    ),
    # --- a barra do painel do PDF (S-528, 2026-09-04): a mesma forma, a segunda tabela
    "icones.ICONES_DO_PDF": (
        TABELA_PERCORRIDA + " (`test_ui_barra_do_pdf`, nos dois sentidos com `barra_do_pdf.ACOES`; "
        "`imagem` a lê por `tracos_de`, no mesmo módulo)"
    ),
    "barra_do_pdf.COM_LIVRO": "um dos três valores que `modo` devolve e `grupos_desligados` consome; quem os distingue é o teste",
    "barra_do_pdf.TRANCADO": "o segundo valor de `modo`, pelo mesmo motivo -- o painel chama `modo(...)`, e não os nomes",
    "sala_declarada.LARGURA_MINIMA_DA_LEITURA": (
        "o piso da coluna de leitura é o **padrão** de `lado_do_tabuleiro` e de "
        "`fracao_para_o_tabuleiro`, e quem as chama não o repete -- passá-lo de fora seria a "
        "segunda declaração do mesmo número. Quem o compara com as partes é o teste"
    ),
    "sala_declarada.ALCA_DO_DIVISOR": (
        "o mesmo caso, e mais estreito: a alça de verdade vem do widget (`handleWidth()`), e este "
        "é o valor que a função responde quando ninguém diz. Um chamador no produto seria o "
        "painel usando o padrão em vez de medir a alça que ele tem"
    ),
    "cabecalho_da_partida.Campo": E_O_TIPO,
    "barra_do_pdf.LEITURA": (
        "o grupo do OCR: o produto o lê pelo campo `grupo` de cada linha da tabela, e só o teste o "
        "nomeia. `VISTA` é a exceção, e por isso não está aqui -- `interruptores_de_vista` filtra por ele"
    ),
}
"""`modulo.NOME -> motivo`, e o motivo não pode ser vazio.

**É um mapa, e não uma lista de perdão.** `test_a_excecao_declarada_ainda_e_orfa` exige que quem
está aqui continue **sem** chamador: um nome que ganhou um e ficou na lista reprova, senão a lista
vira o lugar onde a pergunta deixa de ser feita. É a mesma forma do `RENUMERADOS` de
`tests/test_docs.py`.

**Três motivos se repetem, e são os três que a triagem da S-511 encontrou** ao descer a catraca
de 134 para o número abaixo (2026-09-02): o **tipo** que os clientes usam sem nomear, o
**instrumento** com que uma guarda mede, e a **tabela** que uma guarda percorre inteira. Nenhum
dos três é "falta cliente"; cada um é uma declaração certa que a varredura por identificador não
tem como ver. O que sobra fora deste mapa é pergunta em aberto de verdade.
"""

TETO_DE_ORFAOS = 0
"""Quantos nomes exportados por `ui/` ainda não têm chamador em `src/` **nem resposta escrita**.

**Catraca, e ela só desce.** Medido em 2026-09-01, depois das Fases 73 a 77: **136** nomes sem
chamador em 34 módulos, dos quais **2** estão em `SEM_CHAMADOR` -- então **134** ainda são
pergunta. `ui/desenho_do_tabuleiro.py` contribui com um, e ele é um dos dois declarados. Antes das
fases eram **153**, e aquele módulo sozinho respondia por **18**.

O número aqui é o dos **abertos**, e não o total: ver a regra logo abaixo.

**Medido de novo em 2026-09-02, no primeiro lote da triagem: 134 → 34.** Dos cem que saíram,
**62** deixaram o `__all__` (eram usados dentro do próprio módulo, pelas funções que são a API --
o caso de `HEATMAP_LOW`, repetido em vinte módulos), **26** entraram em `SEM_CHAMADOR` com um dos
três motivos acima, **11** foram apagados (as quatro cores literais e o `box_color` de
`leitura_do_pdf`, o `desvio_de_centralizacao` e a `regiao_de_rolagem` que o canvas do Tk pedia,
`saved_on_page` e `mark_confirmed`, órfãs desde antes do corte, `ligacoes` do `bind_all` e o
`PONTOS_POR_POLEGADA` do `tk scaling`) e **1** ganhou chamador (`SELECTION_HALO_PX`, que
`qt/visor.py` reescrevia como `HALO_DA_SELECAO = 4`). No caminho, duas guardas que o corte tinha
levado voltaram: a do orçamento da S-232 (`fracao_do_documento`, isenta com ela) e a da página
centrada (S-157). E `abas.ABAS` mostrou o que uma declaração sem leitor faz: ainda dizia sete
abas, com a Configuração, que o Qt não tem.
Os 34 que sobravam eram de dois tipos: chamador que mora em `qt/janela.py` ou num painel, e a
mesa do editor de texto, cujas teclas próprias o Qt nunca ligou.

**O segundo lote, no mesmo dia: 34 → 0.** Quatro decisões voltaram a ter chamador em
`qt/janela.py` -- as frases de tirar e devolver caixa (`frase_de_caixa_tirada`,
`frase_de_caixas_devolvidas`, reescritas inline com outro texto), `FRACAO_PADRAO_DO_DIVISOR` (o
padrão era um par de pixels da montagem), `dispositivos_da_janela` (reescrita com `motivo=""`
cravado: "os pesos não estão no disco" saía igual a "o motor é outro") e `abas.ABAS` (a janela
copiava a ordem, e a tupla seguiu declarando a Configuração, que saiu no porte). `conferir_dono`
voltou à montagem dos quatro painéis que declaram ações (S-244). `TECLAS_DO_EDITOR` ganhou quem a
ligue: `Ctrl+B` não fazia nada no editor do Qt, medido, e `SOBREPOSICOES_NO_EDITOR` passou a
decidir, por `teclas_cedidas_ao_editor`, o que a guarda cede ao editor. `degradacao.QUEDAS` voltou
a ter o teste que a percorre, e a linha `pasta_de_pecas` ganhou o dono e a voz que perdeu no
corte. Saíram: `em_destaque` (a `fila_de_destaque` é a API), as duas etiquetas do Tk de
`texto_cores`, `ETIQUETA_DO_LEXICO`, e a metade Tk de `ui/icones.py` (`icone`, o cache de
`PhotoImage`). Cinco ficaram declarados com motivo porque o porte não os trouxe, e o motivo diz o
que falta: o mostrador de corpo (S-292), as listas de escolha exclusiva (S-259/S-262) e a
sequência digitada da paleta (S-248) -- esta última porque **a digitação no editor do Qt ainda
não chega ao documento**, que é o achado maior deste lote e não é órfão: é item.

> **Este número é maior que o do roadmap, e a diferença é o instrumento.** O `ROADMAP_ESTUDO_QT`
> e a `SPEC_ESTUDO_QT` citam **125**, medidos por busca de texto sobre `src/` -- e ali um nome
> citado num docstring conta como uso. Neste projeto os módulos se descrevem uns aos outros em
> prosa o tempo todo, então a busca de texto **subestima**: pela varredura de identificador, que é
> a que esta guarda usa, eram **153**. `margem_de_coordenada` é o exemplo: ela aparecia num
> docstring de `ui/tokens.py`, e a busca de texto a contava como chamada. Os dois números medem
> coisas diferentes e os dois estão certos; o que vale para a catraca é o estrito.

Cada um é uma pergunta em aberto -- *dar chamador, apagar, tirar do `__all__`, ou isentar com
motivo?* --, e nenhuma delas é respondida por esta guarda. O que ela impede é o número **subir**:
exportar um nome novo que ninguém chama passa a falhar, nomeando o módulo e o nome.
"""


def _identificadores(arvore: ast.AST) -> set[str]:
    """Todo nome que aquele módulo **usa** -- variável, atributo, importado ou apelidado.

    Atributo entra pelo `attr` (`desenho.LARGURA_DA_SETA` conta como uso de `LARGURA_DA_SETA`) e
    o importado pelo `name`, porque `from x import Y` é a forma mais comum de uso neste pacote.
    """
    usados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Name):
            usados.add(no.id)
        elif isinstance(no, ast.Attribute):
            usados.add(no.attr)
        elif isinstance(no, ast.alias):
            usados.add(no.name.split(".")[-1])
            if no.asname:
                usados.add(no.asname)
    return usados


def _exportados(arvore: ast.AST) -> list[str]:
    """O `__all__` daquele módulo, ou vazio. Só literal: um `__all__` montado não é declaração."""
    for no in getattr(arvore, "body", []):
        alvos = getattr(no, "targets", [])
        if isinstance(no, ast.Assign) and any(
            isinstance(alvo, ast.Name) and alvo.id == "__all__" for alvo in alvos
        ):
            if isinstance(no.value, (ast.List, ast.Tuple)):
                return [item.value for item in no.value.elts if isinstance(item, ast.Constant)]
    return []


def orfaos() -> dict[str, list[str]]:
    """`modulo.py -> nomes exportados que nenhum outro módulo de `src/` usa`."""
    arvores = {
        caminho: ast.parse(caminho.read_text(encoding="utf-8")) for caminho in RAIZ.rglob("*.py")
    }
    usos = {caminho: _identificadores(arvore) for caminho, arvore in arvores.items()}

    achados: dict[str, list[str]] = {}
    for modulo in sorted(UI.glob("*.py")):
        if modulo.name == "__init__.py":
            continue
        for nome in _exportados(arvores[modulo]):
            if not any(outro != modulo and nome in nomes for outro, nomes in usos.items()):
                achados.setdefault(modulo.name, []).append(nome)
    return achados


def _rotulos(achados: dict[str, list[str]]) -> set[str]:
    return {f"{modulo.removesuffix('.py')}.{nome}" for modulo, nomes in achados.items() for nome in nomes}


class DetectorTests(unittest.TestCase):
    """O detector, afirmado contra fonte de mentira -- a trava da guarda dos inertes (S-505).

    A primeira versão daquela guarda era vácua e passava em verde sobre um comando inerte; a
    lição é que um detector ancorado no arquivo real se apaga junto com o defeito. Estes dois
    casos são literais, e é por isso que continuam valendo quando os órfãos acabarem.
    """

    def test_uso_em_docstring_nao_conta_e_uso_em_codigo_conta(self) -> None:
        modulo = ast.parse('__all__ = ["A", "B", "C"]\nA = 1\nB = 2\nC = 3\n')
        cliente = ast.parse('"""Fala de `A`, de `B` e de `C` na prosa."""\nfrom x import B\nvalor = objeto.C\n')
        usados = _identificadores(cliente)
        self.assertEqual(_exportados(modulo), ["A", "B", "C"])
        self.assertNotIn("A", usados, "citado só no docstring: o `grep` contaria, a guarda não")
        self.assertIn("B", usados, "importado é uso")
        self.assertIn("C", usados, "atributo é uso")

    def test_all_montado_nao_e_declaracao(self) -> None:
        self.assertEqual(_exportados(ast.parse("__all__ = list(nomes)\n")), [])
        self.assertEqual(_exportados(ast.parse("x = 1\n")), [])


class DecisaoOrfaTests(unittest.TestCase):
    """A pergunta que nada fazia, feita."""

    def setUp(self) -> None:
        self.achados = orfaos()
        self.rotulos = _rotulos(self.achados)

    def test_a_varredura_nao_e_vacua(self) -> None:
        """Sem isto, um leitor que deixasse de achar `__all__` faria os outros passarem sobre nada.

        É a lição da S-506: ~20 varreduras ficaram verdes no corte **por passarem sobre lista
        vazia**, e nenhuma delas falhou para dizer isso.
        """
        arvores = [ast.parse(c.read_text(encoding="utf-8")) for c in sorted(UI.glob("*.py"))]
        exportados = sum(len(_exportados(a)) for a in arvores)
        self.assertGreater(exportados, 300, "o leitor de `__all__` deixou de achar os nomes")
        self.assertGreater(len(self.rotulos), 0, "a varredura não achou nenhum órfão -- suspeito")

    def test_o_modulo_do_desenho_nao_tem_decisao_orfa(self) -> None:
        """O módulo que a Fase 73 triou. **Zero**, salvo o que estiver declarado com motivo.

        Ele tinha 18 em 2026-09-01: os doze apelidos de cor (apagados), `COORD_FONT`,
        `COORD_OFFSET_PX`, `margem_de_coordenada`, `LARGURA_DA_SETA` e `PAPEL_DE_SETA` (que
        ganharam chamador nas S-508 e S-510), mais `HEATMAP_LOW`/`HEATMAP_HIGH`, que saíram do
        `__all__` por não serem API -- `heatmap_color` é quem as usa, e ela é a decisão.
        """
        sobraram = sorted(
            rotulo
            for rotulo in _rotulos({"desenho_do_tabuleiro.py": self.achados.get("desenho_do_tabuleiro.py", [])})
            if rotulo not in SEM_CHAMADOR
        )
        self.assertEqual([], sobraram, "decisão pura do desenho sem quem a chame")

    def test_a_excecao_declarada_ainda_e_orfa(self) -> None:
        """O outro lado do mapa: quem ganhou chamador **sai** da lista.

        Sem isto, `SEM_CHAMADOR` viraria o lugar onde a pergunta deixa de ser feita -- e a lista
        cresceria a cada item, que é o oposto do que ela existe para fazer.
        """
        problemas = [
            f"{rotulo} está em SEM_CHAMADOR e já tem chamador"
            for rotulo in SEM_CHAMADOR
            if rotulo not in self.rotulos
        ]
        problemas += [f"{rotulo} está isento sem motivo escrito" for rotulo, m in SEM_CHAMADOR.items() if not m.strip()]
        self.assertEqual([], problemas)

    def test_a_catraca_nao_sobe(self) -> None:
        """O número não pode crescer. Quando alguém tria um, o número desce e a catraca acompanha.

        **Conta o que ainda é pergunta**, e não todo órfão: quem está em `SEM_CHAMADOR` já foi
        olhado e respondido. Ver o docstring de `TETO_DE_ORFAOS`.
        """
        abertos = sorted(self.rotulos - set(SEM_CHAMADOR))
        self.assertLessEqual(
            len(abertos),
            TETO_DE_ORFAOS,
            f"{len(abertos)} nomes exportados sem chamador nem motivo escrito, contra a catraca "
            f"de {TETO_DE_ORFAOS}. Um nome novo em `__all__` precisa de quem o chame -- ou de uma "
            "linha em SEM_CHAMADOR com o motivo.\nOs de agora:\n  " + "\n  ".join(abertos),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
