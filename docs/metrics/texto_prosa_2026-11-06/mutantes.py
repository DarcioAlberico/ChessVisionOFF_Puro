"""Prova por mutação da S-712, **num worktree descartável**, porque ele reescreve o `src/`. Mutante que sobrevive é guarda vácua.

Uso: mutantes.py <raiz do worktree descartável>
"""
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(sys.argv[1])
PY = sys.executable
L, G, M, D = (
    "src/chess_diagram_ocr/text/leitor.py",
    "src/chess_diagram_ocr/text/gigantes.py",
    "src/chess_diagram_ocr/text/moldura.py",
    "src/chess_diagram_ocr/text/duas_linhas.py",
)
MUT = [
    ("sem partir no leitor", L, "descartar_fragmentos(partir_linhas_altas(quebrar_em_linhas(ordem_em_faixa(desta))), escala=escala)", "descartar_fragmentos(quebrar_em_linhas(ordem_em_faixa(desta)), escala=escala)"),
    ("sem sem_gigantes no segmentar", L, "caixas = list(_gigantes.sem_gigantes(caixas, binaria, escala=escala))", "caixas = list(caixas)"),
    ("sem separar_grandes no _tiras", L, "normais, grandes = _gigantes.separar_grandes(desta, escala=escala)", "normais, grandes = list(desta), []"),
    ("_tiras sem escala no leitor", L, "_tiras(caixas, regioes, escala=escala):", "_tiras(caixas, regioes):"),
    ("ALTURA 8->30", G, "ALTURA_DE_GRANDE = 8.0", "ALTURA_DE_GRANDE = 30.0"),
    ("ALTURA 8->5", G, "ALTURA_DE_GRANDE = 8.0", "ALTURA_DE_GRANDE = 5.0"),
    ("FRACAO .3->.6", G, "FRACAO_DA_FOLHA = 0.3", "FRACAO_DA_FOLHA = 0.6"),
    ("FRACAO .3->.1", G, "FRACAO_DA_FOLHA = 0.3", "FRACAO_DA_FOLHA = 0.1"),
    ("FIO .5->2", G, "LARGURA_DE_FIO = 0.5", "LARGURA_DE_FIO = 2.0"),
    ("FIO .5->.1", G, "LARGURA_DE_FIO = 0.5", "LARGURA_DE_FIO = 0.1"),
    ("LETRAS 3->1", G, "LETRAS_DENTRO = 3", "LETRAS_DENTRO = 1"),
    ("LETRAS 3->9", G, "LETRAS_DENTRO = 3", "LETRAS_DENTRO = 9"),
    ("LADO 3->9", G, "LADO_DE_MANCHA = 3.0", "LADO_DE_MANCHA = 9.0"),
    ("TINTA .9->.3", G, "TINTA_DE_MANCHA = 0.9", "TINTA_DE_MANCHA = 0.3"),
    ("TINTA .9->.8", G, "TINTA_DE_MANCHA = 0.9", "TINTA_DE_MANCHA = 0.8"),
    ("TINTA .9->.95", G, "TINTA_DE_MANCHA = 0.9", "TINTA_DE_MANCHA = 0.95"),
    ("sem mancha", G, "    if _e_mancha(caixa, binaria, escala=escala):\n        return True\n", ""),
    ("sem miolo", M, "    limpa[_miolo_da_faixa(mascara)] = 0\n", ""),
    ("VAZADO .5->1", M, "VAZADO_DE_FAIXA = 0.5", "VAZADO_DE_FAIXA = 1.0"),
    ("VAZADO .5->0", M, "VAZADO_DE_FAIXA = 0.5", "VAZADO_DE_FAIXA = 0.0"),
    ("VAZADO .5->.2", M, "VAZADO_DE_FAIXA = 0.5", "VAZADO_DE_FAIXA = 0.2"),
    ("LINHA 1.8->1.0", D, "LINHA_ALTA = 1.8", "LINHA_ALTA = 1.0"),
    ("LINHA 1.8->3", D, "LINHA_ALTA = 1.8", "LINHA_ALTA = 3.0"),
    ("VALE .25->1", D, "VALE_DA_LINHA = 0.25", "VALE_DA_LINHA = 1.0"),
    ("VALE .25->0", D, "VALE_DA_LINHA = 0.25", "VALE_DA_LINHA = 0.0"),
    ("VALE .25->.15", D, "VALE_DA_LINHA = 0.25", "VALE_DA_LINHA = 0.15"),
    ("sem regra da maiuscula", D, "    if all(c.y2 > corte for c in de_cima) or all(c.y1 < corte for c in de_baixo):\n        return [linha]\n", ""),
]
TESTES = ["tests/test_text_linha_intercalada.py", "tests/test_text_moldura.py"]
vivos = []
for nome, arq, velho, novo in MUT:
    p = RAIZ / arq
    orig = p.read_bytes()
    t = orig.decode("utf-8")
    if velho not in t:
        print("NAO ACHOU", nome)
        continue
    p.write_bytes(t.replace(velho, novo, 1).encode("utf-8"))
    r = subprocess.run([PY, "-m", "pytest", *TESTES, "-q", "--no-header", "-x", "-p", "no:cacheprovider"], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace", env={**__import__("os").environ, "PYTHONPATH": str(RAIZ / "src")})
    p.write_bytes(orig)
    morreu = r.returncode != 0
    print(("morreu  " if morreu else "VIVO    "), nome, flush=True)
    if not morreu:
        vivos.append(nome)
print("vivos:", vivos)
