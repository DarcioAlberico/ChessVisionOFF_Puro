"""O dev novo do leiaute: livros da reserva do ouro que passam ao dev (plano B (a), 2026-11-08).

**Por que.** O ouro-teste de 2026-11-06 mostrou que o erro de prosa que sobra é de leiaute (o Tesseract nas linhas certas
erra 0,15%, nas caixas do glifo 1,94%), e o dev de cinco livros não o mostra: o dev dizia 0,23% e o teste disse 2,11%. O
teste não se relê para decidir, então conserto de leiaute precisa de livro novo no dev -- e a reserva é o livro que
nenhum ajuste viu (`docs/ROADMAP_TEXTO_PRECISO.md`, a escolha do dono em 2026-11-08).

**A regra, escrita antes de ler:**

- candidatos: os livros da reserva com diagramação `nova`, nem `fora_do_treino` nem reprovados. Os `vista` têm a
  diagramação de um livro dev e não trazem leiaute novo; o `fora_do_treino` é irmão de série de um livro do teste;
- `ouro.sortear_livros(candidatos, LIVROS, SEMENTE, linguas_inteiras=("spa",))`: o espanhol inteiro (o dev só tem
  inglês e português), e o resto por origem, na proporção dos candidatos, cada origem tomando os primeiros na ordem
  `sha256(semente:identidade)`;
- as folhas de cada livro saem da regra e da admissão do sorteio de 2026-10-30 (`sortear.folhas_do_livro`: três por
  estrato, o outro estrato completando, sem os 8% iniciais e finais);
- o livro que não dá `2 * POR_ESTRATO` folhas, ou que a auditoria visual reprova, cede a vaga ao seguinte da mesma
  origem na mesma ordem, e a fila que acaba deixa a vaga vazia. O reprovado fica na reserva com `reprovado` e
  `fora_do_treino`, como os de 2026-10-30.

**Duas etapas**, porque a auditoria vem antes da gravação e quem confere não é quem sorteia:

1. `--ensaio <pasta>`: escolhe, sorteia e grava `<pasta>/ouro_ensaio.json`, **fora do repositório**. Depois,
   `../texto_ouro_2026-10-30/auditoria.py <pasta>/ouro_ensaio.json <pasta>/auditoria <identidade>...` faz as folhas
   de conferência, e um agente que não sorteou as lê;
2. sem `--ensaio`: grava o manifesto, com os reprovados de `reprovados_auditoria.tsv` desta pasta. Com os mesmos
   reprovados e a mesma `--data`, rodar de novo sobre o manifesto anterior reproduz o mesmo arquivo, byte a byte.

O log (nomes de arquivo, folhas recusadas e o critério de cada recusa) vai para `<log.tsv>`, fora do repositório:
o manifesto só leva identidades.

Uso: dev_novo.py <ouro.json> <log.tsv> [--ensaio=<pasta fora do repositório>] [--data=AAAA-MM-DD]
Raiz com `PDF/` e `PDF Digitais/`: `CVOFF_RAIZ`, ou o repositório onde este script mora.
"""
import csv
import dataclasses
import datetime
import os
import sys

from chess_diagram_ocr.text import ouro

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "texto_ouro_2026-10-30"))
import sortear  # noqa: E402

SEMENTE = "20261120"
LIVROS = 8
"""O dev de 2026-10-30 tem cinco livros e 27 folhas; oito livros de seis folhas mais que dobram o leiaute visto."""
LINGUAS_INTEIRAS = ("spa",)
REPROVADOS = os.path.join(AQUI, "reprovados_auditoria.tsv")
REGRA = (
    f"dev novo = os candidatos da reserva (diagramação nova, nem fora_do_treino nem reprovados) por "
    f"ouro.sortear_livros, {LIVROS} livros, semente {SEMENTE}, {list(LINGUAS_INTEIRAS)} inteiros e o resto por origem "
    "(maior resto) na ordem sha256(semente:identidade); folhas pela regra do sorteio de 2026-10-30; o que não dá 6 "
    "folhas, ou que a auditoria visual reprova (texto_ouro_2026-11-20/reprovados_auditoria.tsv), cede a vaga ao seguinte "
    "da mesma origem, e a fila que acaba deixa a vaga vazia"
)


def ler_reprovados(caminho):
    if not os.path.exists(caminho):
        return {}
    reprovados = {}
    with open(caminho, encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.rstrip("\n")
            if linha and not linha.startswith("#"):
                identidade, motivo = linha.split("\t", 1)
                reprovados[identidade] = motivo
    return reprovados


def candidatos(manifesto):
    return [
        x for x in manifesto.livros
        if x.split == ouro.RESERVA and x.diagramacao == "nova" and not x.fora_do_treino and not x.reprovado
    ]


def escolher(manifesto, caminhos, reprovados, log):
    """Os livros do dev novo e as folhas de cada um, na ordem do sorteio, cedendo a vaga como a regra diz."""
    todos = candidatos(manifesto)
    sorteados = set(ouro.sortear_livros(todos, LIVROS, SEMENTE, linguas_inteiras=LINGUAS_INTEIRAS))
    cotas = {}
    for x in todos:
        if x.identidade in sorteados and x.lingua not in LINGUAS_INTEIRAS:
            cotas[x.origem] = cotas.get(x.origem, 0) + 1
    escolhidos = {}

    def tentar(identidade):
        """Se o livro entra: não está reprovado e dá as folhas. O log diz por que cedeu, quando cede."""
        nome = os.path.basename(caminhos[identidade])
        if identidade in reprovados:
            log.writerow([identidade, nome, "cede a vaga", reprovados[identidade]])
            return False
        _, folhas, recusadas = sortear.folhas_do_livro((identidade, str(caminhos[identidade])))
        for folha, criterio in recusadas:
            log.writerow([identidade, nome, f"folha {folha} recusada", criterio])
        if len(folhas) < 2 * sortear.POR_ESTRATO:
            log.writerow([identidade, nome, "cede a vaga", f"{len(folhas)} folhas"])
            return False
        escolhidos[identidade] = folhas
        log.writerow([identidade, nome, "entra", " ".join(f"{f}:{e}" for f, e in folhas)])
        return True

    # As línguas inteiras primeiro: o livro delas que cede passa a vaga ao seguinte da mesma origem, como os outros.
    for x in todos:
        if x.lingua in LINGUAS_INTEIRAS and not tentar(x.identidade):
            cotas[x.origem] = cotas.get(x.origem, 0) + 1
    for origem in sorted(cotas):
        fila = ouro.ordem_dos_livros(
            [x.identidade for x in todos if x.origem == origem and x.lingua not in LINGUAS_INTEIRAS], SEMENTE)
        tomados = 0
        for identidade in fila:
            if tomados >= cotas[origem]:
                break
            tomados += tentar(identidade)
    return ouro.ordem_dos_livros(escolhidos, SEMENTE), escolhidos


def main(manifesto_json, log_tsv, *opcoes):
    estranhas = [op for op in opcoes if not op.startswith(("--ensaio=", "--data="))]
    if estranhas:
        raise SystemExit(f"opções desconhecidas: {estranhas} (as que existem: --ensaio=<pasta>, --data=AAAA-MM-DD)")
    valor = dict(op[2:].split("=", 1) for op in opcoes)
    data = valor.get("data") or datetime.date.today().isoformat()
    datetime.date.fromisoformat(data)
    m = ouro.carregar(manifesto_json)
    if any(x.split == ouro.DEV and x.entrou_em for x in m.livros):
        raise SystemExit("o manifesto já tem livro que entrou no dev: rode sobre o manifesto de antes do dev novo")
    reprovados = ler_reprovados(REPROVADOS)
    pastas = [os.path.join(sortear.RAIZ, "PDF Digitais"), os.path.join(sortear.RAIZ, "PDF")]
    caminhos = ouro.localizar([x.identidade for x in candidatos(m)], pastas)
    faltam = sorted({x.identidade for x in candidatos(m)} - set(caminhos))
    if faltam:
        raise SystemExit(f"candidatos que não se acham em {pastas}: {faltam}")
    with open(log_tsv, "w", encoding="utf-8", newline="") as arquivo:
        log = csv.writer(arquivo, delimiter="\t", lineterminator="\n")
        ordem, escolhidos = escolher(m, caminhos, reprovados, log)
    novo = m
    for identidade in ordem:
        novo = ouro.acrescentar_ao_dev(novo, identidade, escolhidos[identidade], entrou_em=data,
                                       folhas_minimas=2 * sortear.POR_ESTRATO)
    para_reprovar = {i for i in reprovados if any(x.identidade == i and x.split == ouro.RESERVA for x in novo.livros)}
    novo = dataclasses.replace(
        novo,
        livros=tuple(
            dataclasses.replace(x, reprovado=reprovados[x.identidade], fora_do_treino=True)
            if x.identidade in para_reprovar else x
            for x in novo.livros
        ),
        sorteio={**novo.sorteio, "dev_novo": {"data": data, "semente": SEMENTE, "meta": LIVROS, "entraram": len(ordem),
                                               "regra": REGRA}},
    )
    erros = ouro.problemas(novo)
    assert not erros, erros
    if "ensaio" in valor:
        os.makedirs(valor["ensaio"], exist_ok=True)
        destino = os.path.join(valor["ensaio"], "ouro_ensaio.json")
    else:
        destino = manifesto_json
    ouro.gravar(novo, destino)
    print(f"{len(ordem)} livros passam ao dev em {data}, {sum(len(escolhidos[i]) for i in ordem)} folhas -> {destino}")
    print("identidades:", " ".join(ordem))


if __name__ == "__main__":
    main(*sys.argv[1:])
