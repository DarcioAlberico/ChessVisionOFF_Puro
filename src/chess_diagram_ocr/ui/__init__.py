"""Componentes de interface reaproveitáveis entre os frontends.

O que mora aqui é o que a Fase 4 precisou tirar de dentro do `app_tkinter.py`: o estado
persistido (S-25), a explicação de legalidade em pt-BR (S-21) e o tabuleiro interativo
(S-20). A decomposição completa da UI é da Fase 6 (S-31); este pacote é o começo dela, e
existe porque os três itens acima são testáveis e o `app_tkinter.py` não é.
"""
