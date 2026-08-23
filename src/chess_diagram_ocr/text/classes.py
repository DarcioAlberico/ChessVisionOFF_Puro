"""As classes de caractere: o mapa entre caractere e nome de pasta (S-180).

**Isto não é um alfabeto, é um esquema de nomes de pasta do Windows** -- e é onde a base de
treino inteira se ancora. Cada classe do modelo é uma pasta com os recortes dela, e
`folder_to_char` é o que traduz o nome de volta. Errar a tradução não dá erro: dá outra letra.

O porte é **literal**, e a razão está nos três acidentes que deram esta forma a ele no projeto
de origem:

1. **`sym_f7` guardava 127 imagens da casa de xadrez `f7`**, não do hexadecimal `÷`. Como
   `chr(int("f7"))` levanta, elas viravam `"?"` e colidiam com `sym_63`, que é o `?` de verdade
   -- duas classes distintas ensinando o mesmo símbolo. Corrigir o rótulo fez o modelo **já
   treinado** acertar 127 de 127, sem retreinar.
2. **`folder_to_char` devolvia `"?"` em silêncio** quando não entendia a pasta, e foi isso que
   deixou o acidente acima passar despercebido. Daí o `strict=True`, que levanta.
3. **`lower_ä` ficou vazia** porque `cv2.imwrite` devolve `False` em caminho não-ASCII no
   Windows, sem levantar. É a razão de ser da regra de nomes só-ASCII aqui.

**Alargar `EXTRAS_LEGIVEIS` faria as duas bases divergirem sem aviso**, e a de `training_data/`
-- 608.407 recortes em 314 pastas, medidos em 2026-08-23 -- deixaria de ser legível por este
projeto. A lista é fechada; `tests/test_text_classes.py` a trava.
"""

from __future__ import annotations

#: Não alfanuméricos que ainda cabem num nome de pasta legível.
#:
#: São os que este material cola no caractere seguinte: o hífen da notação longa (`Rf1-g1`) e o
#: par de avaliação `+-` / `-+`. Sem eles a base guardava `ligature_hex_002d0067` no lugar de
#: `ligature_-g` -- e quem revisa a base a olho lê o nome da pasta, não este arquivo.
#:
#: **A lista é fechada de propósito**, e é curta porque um candidato novo tem de passar por três
#: filtros:
#:
#: - **legal no Windows**: `\ / : * ? " < > |` não são nome de pasta, e ponto ou espaço no fim
#:   somem sem aviso;
#: - **inerte no `glob`**: quem varre a base monta o padrão com o caminho inteiro, então `*`,
#:   `?`, `[` e `]` no nome da pasta virariam curinga e a classe apareceria vazia;
#: - **nunca `_`**: é o que garante que um nome legível não comece por `hex_` e seja lido de
#:   volta como hexadecimal.
EXTRAS_LEGIVEIS = "+-"

#: Pastas de formatos antigos cujo caractere real foi confirmado olhando as amostras.
LEGADO = {
    "sym_f7": "f7",
}

#: Caracteres que o Windows recusa num nome de pasta. Ver `nome_e_legal_no_windows`.
PROIBIDOS_NO_WINDOWS = '\\/:*?"<>|'


class NomeDePastaInvalido(ValueError):
    """O nome da pasta não corresponde a nenhum caractere conhecido."""


def char_to_folder(char: str) -> str:
    """Converte um caractere em nome de pasta seguro para Windows, distinguindo caixa.

    Mantém apenas alfanuméricos ASCII puros como legíveis; todo o resto vira `sym_{ord}`.
    Ligaduras (mais de um caractere) viram `ligature_{char}` quando cabem, e
    `ligature_hex_{...}` quando não.
    """
    if not char:
        return "unknown"

    # Ligaduras (ex.: 'fi', 'ffi', 'f7', '-g')
    if len(char) > 1:
        # Cabe no nome da pasta e fica legível. O teste já foi `isalpha()`, que jogava 'f7' --
        # casa de xadrez, comum como box único nestes livros -- no ramo hexadecimal; depois
        # `isalnum()`, que fazia o mesmo com '-g'.
        if char.isascii() and all(c.isalnum() or c in EXTRAS_LEGIVEIS for c in char):
            return f"ligature_{char}"
        # Hex de largura fixa: com largura variável a volta é ambígua ('ab' + 'c' e 'a' + 'bc'
        # geram a mesma cadeia).
        hex_str = "".join(f"{ord(c):04x}" for c in char)
        return f"ligature_hex_{hex_str}"

    # Apenas A-Z, a-z e 0-9 são mantidos "legíveis".
    if "A" <= char <= "Z":
        return f"upper_{char}"
    if "a" <= char <= "z":
        return f"lower_{char}"
    if "0" <= char <= "9":
        return f"digit_{char}"
    # Qualquer outro (acentos, símbolos, pontuação, espaço) vira código do ponto de código.
    return f"sym_{ord(char)}"


def folder_to_char(folder_name: str, strict: bool = False) -> str:
    """Converte um nome de pasta de volta para o caractere original.

    `upper_A` -> `A`, `lower_a` -> `a`, `digit_1` -> `1`, `sym_46` -> `.`.

    Com `strict=True`, levanta `NomeDePastaInvalido` em vez de devolver `"?"`. **Devolver `"?"`
    em silêncio é o que permitiu 127 amostras treinarem a classe errada sem ninguém notar**; a
    validação do dataset usa o modo estrito, e quem carrega um metadado também.
    """

    def falhar() -> str:
        if strict:
            raise NomeDePastaInvalido(folder_name)
        return "?"

    if folder_name in LEGADO:
        return LEGADO[folder_name]

    if folder_name.startswith("ligature_hex_"):
        hex_str = folder_name[13:]
        if len(hex_str) % 4 != 0:
            return falhar()
        try:
            return "".join(chr(int(hex_str[i : i + 4], 16)) for i in range(0, len(hex_str), 4))
        except ValueError:
            return falhar()

    if folder_name.startswith("ligature_"):
        return folder_name[9:]

    if folder_name.startswith(("upper_", "lower_", "digit_")):
        return folder_name[6:]

    if folder_name.startswith("sym_"):
        try:
            return chr(int(folder_name[4:]))
        except ValueError:
            return falhar()

    if folder_name.startswith("ASCII_"):
        # Compatibilidade com formato antigo.
        try:
            return chr(int(folder_name[6:]))
        except ValueError:
            return falhar()

    # Formato antigo (pasta = caractere diretamente).
    return folder_name


def nome_e_legal_no_windows(nome: str) -> bool:
    """O nome pode ser uma pasta no Windows?

    Três coisas, e as três já morderam a base de origem: caractere proibido, ponto ou espaço no
    fim (que o Windows remove **sem avisar**, colidindo duas classes numa), e nome vazio.
    """
    if not nome:
        return False
    if any(c in PROIBIDOS_NO_WINDOWS for c in nome):
        return False
    return nome[-1] not in ". "
