"""O mapa entre caractere e nome de pasta, conferido contra as classes reais (S-180).

**Por que os testes daqui usam o `models/char_meta.json` e não exemplos escolhidos.** O risco
deste módulo não é errar num caso que alguém pensaria em testar -- é errar num caso que ninguém
pensaria, que foi exatamente o que aconteceu no projeto de origem: `sym_f7` guardava 127 imagens
da casa de xadrez `f7`, e a classe treinou errada por meses. O conjunto certo de exemplos é a
lista inteira de classes do modelo.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from chess_diagram_ocr.text.classes import (
    EXTRAS_LEGIVEIS,
    LEGADO,
    PROIBIDOS_NO_WINDOWS,
    NomeDePastaInvalido,
    char_to_folder,
    folder_to_char,
    nome_e_legal_no_windows,
)

META = Path(__file__).resolve().parents[1] / "models" / "char_meta.json"


def classes_do_modelo() -> list[str]:
    if not META.exists():  # pragma: no cover - checkout sem o metadado
        return []
    dados = json.loads(META.read_text(encoding="utf-8"))
    return [str(v) for v in dados["idx_to_char"].values()]


class VoltaFechaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.classes = classes_do_modelo()
        if not self.classes:
            self.skipTest("models/char_meta.json não existe neste checkout")

    def test_a_volta_fecha_para_todas_as_classes_do_metadado(self) -> None:
        """`folder_to_char(char_to_folder(c)) == c` para toda classe que o modelo conhece."""
        quebradas = []
        for char in self.classes:
            pasta = char_to_folder(char)
            de_volta = folder_to_char(pasta, strict=True)
            if de_volta != char:
                quebradas.append(f"{char!r} -> {pasta!r} -> {de_volta!r}")
        self.assertEqual([], quebradas)

    def test_todo_nome_e_legal_no_windows(self) -> None:
        """Um nome ilegal não vira pasta, e a classe some da base sem nada acusar."""
        ilegais = [char_to_folder(c) for c in self.classes if not nome_e_legal_no_windows(char_to_folder(c))]
        self.assertEqual([], ilegais)

    def test_nenhum_nome_de_pasta_colide(self) -> None:
        """Duas classes com o mesmo nome de pasta seriam duas classes treinando uma pasta só."""
        pastas: dict[str, str] = {}
        colisoes = []
        for char in self.classes:
            pasta = char_to_folder(char)
            if pasta in pastas and pastas[pasta] != char:
                colisoes.append(f"{pasta!r}: {pastas[pasta]!r} e {char!r}")
            pastas[pasta] = char
        self.assertEqual([], colisoes)

    def test_nenhum_nome_de_pasta_e_curinga_de_glob(self) -> None:
        """`*`, `?`, `[` e `]` no nome esvaziariam a classe na varredura da base (S-200)."""
        curingas = [p for p in map(char_to_folder, self.classes) if any(c in p for c in "*?[]")]
        self.assertEqual([], curingas)

    def test_as_classes_de_ligadura_existem_e_sao_muitas(self) -> None:
        """Um porte que perdesse o ramo de ligadura passaria em tudo acima e leria 135 classes.

        São ligadura tipográfica (`fi`, `ffl`), casa de xadrez colada (`e4`, `xf6`) e par de
        avaliação (`+-`). Elas somam mais de um terço do modelo, e a S-186 depende de saber
        disso: uma classe de par concorre com o separador de glifo colado.
        """
        ligaduras = [c for c in self.classes if len(c) > 1]
        self.assertGreater(len(ligaduras), len(self.classes) // 4)
        self.assertIn("fi", ligaduras)


class ListaFechadaTests(unittest.TestCase):
    def test_a_lista_de_extras_legiveis_e_fechada(self) -> None:
        """**Alargar esta lista faz as duas bases divergirem sem aviso.**

        Um candidato novo tem de passar por três filtros -- legal no Windows, inerte no `glob`,
        e nunca `_` (que é o que impede um nome legível de começar por `hex_` e ser lido de volta
        como hexadecimal). Se algum dia a lista mudar, ela muda **aqui e lá**, e a base de 700
        mil é migrada junto; senão as pastas antigas deixam de decodificar.
        """
        self.assertEqual("+-", EXTRAS_LEGIVEIS)

    def test_o_legado_cobre_o_caso_que_treinou_a_classe_errada(self) -> None:
        """`sym_f7` são 127 imagens da casa `f7`, e não do hexadecimal. Ver o cabeçalho."""
        self.assertEqual("f7", LEGADO["sym_f7"])
        self.assertEqual("f7", folder_to_char("sym_f7", strict=True))


class ModoEstritoTests(unittest.TestCase):
    """Devolver `"?"` em silêncio é o que deixou o defeito do `sym_f7` passar."""

    def test_pasta_desconhecida_levanta_em_vez_de_devolver_interrogacao(self) -> None:
        for pasta in ("sym_naoehnumero", "ligature_hex_abc", "ASCII_xx"):
            with self.subTest(pasta=pasta):
                with self.assertRaises(NomeDePastaInvalido):
                    folder_to_char(pasta, strict=True)
                self.assertEqual("?", folder_to_char(pasta))

    def test_o_hexadecimal_e_de_largura_fixa(self) -> None:
        """Com largura variável a volta é ambígua: `ab`+`c` e `a`+`bc` dariam a mesma cadeia."""
        self.assertEqual("ligature_hex_00e70061", char_to_folder("ça"))
        self.assertEqual("ça", folder_to_char("ligature_hex_00e70061", strict=True))
        # Comprimento que não é múltiplo de 4 não é decodificável, e dizê-lo é o ponto.
        with self.assertRaises(NomeDePastaInvalido):
            folder_to_char("ligature_hex_00e7006", strict=True)


class NomeLegalTests(unittest.TestCase):
    def test_ponto_ou_espaco_no_fim_e_ilegal(self) -> None:
        """O Windows os remove **sem avisar**, e duas classes viram uma."""
        self.assertFalse(nome_e_legal_no_windows("sym_46."))
        self.assertFalse(nome_e_legal_no_windows("lower_a "))
        self.assertTrue(nome_e_legal_no_windows("lower_a"))

    def test_os_proibidos_do_windows_sao_recusados(self) -> None:
        for proibido in PROIBIDOS_NO_WINDOWS:
            with self.subTest(proibido=proibido):
                self.assertFalse(nome_e_legal_no_windows(f"lower{proibido}a"))

    def test_caractere_vazio_tem_nome_proprio(self) -> None:
        self.assertEqual("unknown", char_to_folder(""))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
