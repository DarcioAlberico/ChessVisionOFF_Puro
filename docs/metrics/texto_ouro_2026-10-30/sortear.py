"""O sorteio do ouro da S-702: os livros do teste entre os da D6, e as folhas de cada um.

Lê o inventário da D6 (feito sem leitor: metadados, fontes, perfil de admissão; uma linha por PDF com
`destino`, `serie`, `origem` e `lingua`) e as folhas dev do relatório de 2026-10-30, sorteia com
`chess_diagram_ocr.text.ouro` e admite com `chess_diagram_ocr.text.admissao`. O estrato de cada folha
sai do classificador de token do protótipo (`texto_prosa_2026-10-30/banco.py`), até a régua das
S-700/S-701 entrar no pacote; o sha256 dele vai para o manifesto.

O manifesto só leva identidades (decisão do dono: o repositório é público). Os nomes, as folhas
recusadas e o critério de cada recusa vão para `<log>`, que fica fora do repositório.

A auditoria visual faz parte da elegibilidade: `[reprovados.tsv]` (identidade, tab, motivo) lista os
livros que ela reprovou. Um livro sorteado e reprovado cede a vaga como o que não dá seis folhas, e fica
na reserva com `reprovado` e `fora_do_treino`.

Depois de congelado, o manifesto não se sorteia de novo com livros a mais: o livro que chegar (a terceira
língua pendente) entra pelo `acrescentar.py`, que não mexe em nada sorteado. Rodar este script outra vez
com o mesmo inventário e os mesmos reprovados reproduz o manifesto de antes do acréscimo, byte a byte.

Uso: sortear.py <inventario_d6.tsv> <saida_ouro.json> <log.tsv> [reprovados.tsv]
Raiz com `PDF/` e `PDF Digitais/`: `CVOFF_RAIZ`, ou o repositório onde este script mora.
"""
import csv
import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import fitz

from chess_diagram_ocr.text import admissao, ouro
from chess_diagram_ocr.text.caderno import identidade_de
from chess_diagram_ocr.text.leitor import ler_pagina

AQUI = os.path.dirname(os.path.abspath(__file__))
REGUA = os.path.join(AQUI, "..", "texto_prosa_2026-10-30")
sys.path.insert(0, REGUA)
import banco  # noqa: E402

# o checkout que tem PDF/ e PDF Digitais/: CVOFF_RAIZ, ou o repositório onde este script mora
RAIZ = os.environ.get("CVOFF_RAIZ") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SEMENTE = "20261030"
CONGELADO_EM = "2026-10-30"
"""A data do congelamento, e não a da corrida: rodar de novo reproduz o mesmo manifesto."""
LIVROS_NO_TESTE = 16
"""A meta é 12 (G102); quatro de folga para a auditoria visual, que reprova o livro inteiro."""
LINGUAS_INTEIRAS = ("por", "spa")
POR_ESTRATO = 3
RELATORIO = os.path.join(AQUI, "..", "texto_prosa_20261030.json")


def sha(caminho):
    with open(caminho, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def retangulos_de_diagrama(pdf, indice):
    """Os retângulos de diagrama da montagem da camada, em pontos do PDF (a unidade dela é `pt`).

    Uma folha que o leitor recusa fica sem retângulo -- e então só a fileira protege.
    """
    try:
        pagina = ler_pagina(pdf, indice, motor="camada")
    except Exception:  # noqa: BLE001 -- o sorteio não cai por uma folha que o leitor recusa
        return []
    assert pagina.unidade == "pt", pagina.unidade
    return [tuple(d.bbox) for d in pagina.diagramas]


def folhas_do_livro(args):
    """As folhas sorteadas de um livro, e as recusadas pela admissão (para o log)."""
    identidade, pdf = args
    doc = fitz.open(pdf)
    perfil = admissao.perfil_do_livro(doc)
    produtor = admissao.produtor_de(doc)
    recusadas = []

    def estrato_de(folha):
        return ouro.estrato_do_texto(doc[folha - 1].get_text(), banco.classe_do_token)

    def admitida(folha):
        a = admissao.admitir_folha(doc[folha - 1], retangulos_de_diagrama(pdf, folha - 1),
                                   produtor=produtor, perfil=perfil)
        if not a.admitida:
            recusadas.append((folha, a.criterio))
        return a.admitida

    escolhidas = ouro.sortear_folhas(identidade, doc.page_count, estrato_de, admitida, por_estrato=POR_ESTRATO)
    return identidade, escolhidas, recusadas


def main(inventario, saida, log, reprovados_tsv=None):
    reprovados = {}
    if reprovados_tsv:
        for linha in open(reprovados_tsv, encoding="utf-8"):
            if linha.strip() and not linha.startswith("#"):
                identidade, motivo = linha.rstrip("\r\n").split("\t", 1)  # o checkout no Windows o traz em CRLF
                reprovados[identidade] = motivo
    pdf_dir, d6_dir = os.path.join(RAIZ, "PDF"), os.path.join(RAIZ, "PDF Digitais")
    linhas = list(csv.DictReader(open(inventario, encoding="utf-8"), delimiter="\t"))
    caminho = {}
    nome = {}
    for linha in linhas:
        if linha["destino"] == "fora":
            continue
        pdf = os.path.join(d6_dir, linha["arquivo"])
        linha["identidade"] = identidade_de(pdf)
        caminho[linha["identidade"]] = pdf
        nome[linha["identidade"]] = linha["arquivo"]

    # o dev: as folhas de prosa e do estrato misto do relatório de 2026-10-30
    rel = json.load(open(RELATORIO, encoding="utf-8"))
    dev_livros, dev_folhas, dev_origem = {}, [], {}
    for conjunto, estrato in (("ouro_dev_completo", ouro.PROSA), ("ouro_dev_estrato_misto", ouro.MISTO)):
        for arquivo, dados in rel["conjuntos"][conjunto]["por_livro"].items():
            identidade = identidade_de(os.path.join(pdf_dir, arquivo))
            assert identidade, f"livro dev ausente: {arquivo}"
            dev_livros[identidade] = dados["lingua"]
            nome[identidade] = arquivo
            produtor = admissao.produtor_de(fitz.open(os.path.join(pdf_dir, arquivo)))
            dev_origem[identidade] = "ebook" if produtor.lower().startswith("calibre") else "pdf"
            if identidade in reprovados:  # a camada dele não é a tinta: sai do dev, e as folhas com ele
                continue
            dev_folhas += [ouro.FolhaDoOuro(identidade, f, dados["lingua"], estrato, ouro.DEV) for f in dados["folhas"]]
    # as folhas dev não foram sorteadas agora, mas passam pela mesma admissão: a que não passa para tudo
    for folha in dev_folhas:
        pdf = os.path.join(pdf_dir, nome[folha.identidade])
        doc = fitz.open(pdf)
        a = admissao.admitir_folha(doc[folha.folha - 1], retangulos_de_diagrama(pdf, folha.folha - 1),
                                   produtor=admissao.produtor_de(doc), perfil=admissao.perfil_do_livro(doc))
        assert a.admitida, f"folha dev {folha.folha} de {folha.identidade} recusada: {a.criterio}"
    dvoretsky = next(i for i, n in nome.items() if n.startswith("Dvoretsky") and i in dev_livros)

    # os grupos: a série aponta para o seu representante; a diagramação do Dvoretsky, para ele
    representante = {linha["serie"]: linha["identidade"] for linha in linhas if linha["destino"] == "candidato"}
    candidatos, outros = [], {}
    # o candidato primeiro: a cópia idêntica de outro arquivo tem a mesma identidade e não pode tomar o lugar dele
    for linha in sorted(linhas, key=lambda x: x["destino"] != "candidato"):
        if linha["destino"] == "fora" or linha["identidade"] in outros or linha["identidade"] in dev_livros:
            continue
        origem = "ebook" if linha["origem"].startswith("ebook") else "pdf"
        if linha["destino"] == "diagramacao_dev":
            livro = ouro.LivroDoOuro(linha["identidade"], ouro.RESERVA, linha["lingua"], origem, "vista", dvoretsky)
        else:
            grupo = representante[linha["serie"]]
            livro = ouro.LivroDoOuro(linha["identidade"], ouro.RESERVA, linha["lingua"], origem, "nova",
                                     "" if grupo == linha["identidade"] else grupo)
            if linha["destino"] == "candidato":
                candidatos.append(livro)
        outros[livro.identidade] = livro

    # o sorteio dos livros, e a troca do que não tem seis folhas, ou foi reprovado na auditoria, pelo
    # seguinte em inglês da mesma origem
    ordem = ouro.sortear_livros(candidatos, LIVROS_NO_TESTE, SEMENTE, linguas_inteiras=LINGUAS_INTEIRAS)
    fila = ouro.ordem_dos_livros([c.identidade for c in candidatos], SEMENTE)
    por_id = {c.identidade: c for c in candidatos}
    teste, folhas_teste, registro, tentados = [], [], [], set()
    pendentes = list(ordem)
    with ProcessPoolExecutor(8) as ex:
        while pendentes:
            tentados.update(pendentes)
            aceitos = [i for i in pendentes if i not in reprovados]
            resultados = list(ex.map(folhas_do_livro, [(i, caminho[i]) for i in aceitos]))
            resultados += [(i, [], [("auditoria", reprovados[i])]) for i in pendentes if i in reprovados]
            pendentes = []
            for identidade, escolhidas, recusadas in resultados:
                livro = por_id[identidade]
                registro.append((identidade, escolhidas, recusadas))
                if len(escolhidas) == 2 * POR_ESTRATO:
                    teste.append(identidade)
                    folhas_teste += [ouro.FolhaDoOuro(identidade, f, livro.lingua, e, ouro.TESTE) for f, e in escolhidas]
                    continue
                # a vaga de uma língua inteira que não deu folha vai ao seguinte em inglês da mesma origem
                troca = next((i for i in fila if i not in tentados and por_id[i].origem == livro.origem
                              and por_id[i].lingua not in LINGUAS_INTEIRAS), None)
                if troca:
                    pendentes.append(troca)
                    tentados.add(troca)

    grupos_do_teste = {outros[i].grupo or i for i in teste}
    livros = [ouro.LivroDoOuro(i, ouro.DEV, lingua, dev_origem[i]) if i not in reprovados else
              ouro.LivroDoOuro(i, ouro.RESERVA, lingua, dev_origem[i], fora_do_treino=True, reprovado=reprovados[i])
              for i, lingua in sorted(dev_livros.items())]
    for identidade, livro in sorted(outros.items()):
        if identidade in teste:
            livros.append(ouro.LivroDoOuro(**{**vars(livro), "split": ouro.TESTE}))
        elif identidade in reprovados:
            livros.append(ouro.LivroDoOuro(**{**vars(livro), "fora_do_treino": True, "reprovado": reprovados[identidade]}))
        else:
            fora = (livro.grupo or identidade) in grupos_do_teste
            livros.append(ouro.LivroDoOuro(**{**vars(livro), "fora_do_treino": fora}))
    linguas = {outros[i].lingua for i in teste}
    pendencias = (ouro.PENDENCIA_DE_LINGUA,) if len(linguas) < ouro.LINGUAS_MINIMAS_NO_TESTE else ()
    ordem_teste = {i: k for k, i in enumerate(ouro.ordem_dos_livros(teste, SEMENTE))}
    folhas_teste.sort(key=lambda f: (ordem_teste[f.identidade], ouro.ESTRATOS.index(f.estrato), f.folha))
    manifesto = ouro.Manifesto(
        versao=ouro.VERSAO,
        congelado_em=CONGELADO_EM,
        primeira_leitura_do_teste=None,
        pendencias=pendencias,
        livros=tuple(livros),
        folhas=tuple(dev_folhas + folhas_teste),
        sorteio={
            "semente": SEMENTE,
            "livros": f"teste = todos os candidatos em {list(LINGUAS_INTEIRAS)} + os primeiros por origem (maior resto) "
                      f"na ordem sha256(semente:identidade), {LIVROS_NO_TESTE} no total; o que não dá "
                      f"{2 * POR_ESTRATO} folhas, ou que a auditoria visual reprova (reprovados_auditoria.tsv), cede a vaga ao "
                      "seguinte em inglês da mesma origem; o livro da "
                      "língua pendente, quando chegar, entra a mais, sem trocar nenhum sorteado",
            "folhas": f"ordem sha256(identidade + folha), folha em base 1, sem os {ouro.PULAR:.0%} iniciais e finais; "
                      f"{POR_ESTRATO} por estrato, o outro estrato completando",
            "estratos": {"prosa": list(ouro.ESTRATO_PROSA), "misto": list(ouro.ESTRATO_MISTO)},
            "classificador_de_token": {"arquivo": "docs/metrics/texto_prosa_2026-10-30/banco.py",
                                       "sha256": sha(os.path.join(REGUA, "banco.py"))[:16]},
            "admissao": f"chess_diagram_ocr.text.admissao versao {admissao.VERSAO}",
            "candidatos": len(candidatos),
            "dev": "as folhas de ouro_dev_completo (prosa) e ouro_dev_estrato_misto (misto) de "
                   "docs/metrics/texto_prosa_20261030.json",
        },
    )
    erros = ouro.problemas(manifesto)
    assert not erros, erros
    ouro.gravar(manifesto, saida)
    with open(log, "wb") as f:
        f.write(b"identidade\tsplit\tarquivo\tfolhas\trecusadas\n")
        for identidade, escolhidas, recusadas in registro:
            split = "teste" if identidade in teste else "trocado"
            f.write((f"{identidade}\t{split}\t{nome[identidade]}\t{escolhidas}\t{recusadas}\n").encode())
        for livro in livros:
            if livro.split != ouro.TESTE and livro.identidade not in {r[0] for r in registro}:
                f.write((f"{livro.identidade}\t{livro.split}{'/fora_do_treino' if livro.fora_do_treino else ''}"
                         f"\t{nome[livro.identidade]}\t\t\n").encode())
    print(f"teste: {len(teste)} livros, {len(folhas_teste)} folhas; dev: {len(set(dev_livros) - set(reprovados))} livros, "
          f"{len(dev_folhas)} folhas; reserva: {sum(x.split == ouro.RESERVA for x in livros)}; trocas: "
          f"{len(registro) - len(teste)}")


if __name__ == "__main__":
    main(*sys.argv[1:5])
