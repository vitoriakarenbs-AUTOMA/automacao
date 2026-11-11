# -*- coding: utf-8 -*-
"""Qual robô está atendendo esta conversa, para a tela poder dizer.

Pam, 08/10/2026: "o Otto ainda não está aparecendo no front end, aparece apenas o Sebastião".
Cobrado de novo em 07/11/2026: "estou vendo eles sem atendimento".

O DEFEITO
A tela decide o nome do robô olhando o **número** de WhatsApp: `numero.agente` só tem dois
valores, `sebastiao` e `alicia`. Mas o Otto não é do número: ele é escolhido **por conversa**,
no servidor (`usa_otto` em atendimento.py: veio da campanha do desbloqueio, já recebeu o vídeo
de GR, falou a frase do anúncio, ou o caso é de gerenciadora). Essa decisão nunca chegava à
tela, então a senhora abria uma conversa de GR que o Otto estava atendendo e lia "Sebastião".

O segundo pedaço: as mensagens da IA eram gravadas **sem o campo que diz qual robô falou**.
Medido em 07/11: 128 mensagens da IA hoje, todas sem esse campo. O código já calculava o nome
para assinar a mensagem no WhatsApp ("Aqui é o Otto, QAP"); ele só não guardava no card.

ESTE MÓDULO É PURO de propósito: só regra, sem banco e sem rede, para a tela e o servidor
concordarem sempre e para o teste não precisar de nada montado.
"""

OTTO, SEBASTIAO, ALICIA = 'otto', 'sebastiao', 'alicia'

# Como cada um aparece para a equipe. O acento importa: é o que a pessoa lê na tela.
ROTULO = {OTTO: 'Otto', SEBASTIAO: 'Sebastião', ALICIA: 'Alícia'}

# A campanha que o Otto atende. Mesmo valor que atendimento.CAMPANHA_DESBLOQUEIO.
CAMPANHA_DESBLOQUEIO = 'Campanha Desbloqueio GR'


def normalizar(autor):
    """Aceita como o campo foi gravado ao longo do tempo: 'otto', 'Otto', 'sebastiao:algo'."""
    a = (autor or '').strip().lower()
    if not a:
        return None
    a = a.split(':')[0]
    return a if a in ROTULO else None


def quem_falou(autores_da_ia):
    """O último robô que falou, pela ordem em que as mensagens vieram. None se não dá para saber.

    Lê de trás para frente porque quem manda é o último: uma conversa que começou com o
    Sebastião e passou para o Otto está com o Otto.
    """
    for a in reversed(list(autores_da_ia or [])):
        n = normalizar(a)
        if n:
            return n
    return None


def robo(autores_da_ia=(), origem='', agente_do_numero=SEBASTIAO):
    """Qual robô mostrar, na ordem do que se sabe com mais certeza.

    1. quem de fato falou nesta conversa (o campo gravado na mensagem);
    2. sem isso, a campanha de origem: quem veio do desbloqueio é do Otto;
    3. sem isso, o robô configurado no número, que é o que a tela já fazia sozinha.

    A ordem importa: conversa antiga não tem o campo gravado (ele só passou a existir em
    07/11/2026), e para essas a origem é a melhor informação disponível.
    """
    falou = quem_falou(autores_da_ia)
    if falou:
        return falou
    if (origem or '').strip() == CAMPANHA_DESBLOQUEIO:
        return OTTO
    a = (agente_do_numero or '').strip().lower()
    return ALICIA if a == ALICIA else SEBASTIAO


def rotulo_de(autores_da_ia=(), origem='', agente_do_numero=SEBASTIAO):
    """O nome como a equipe lê na tela."""
    return ROTULO[robo(autores_da_ia, origem, agente_do_numero)]


def autor_para_gravar(motor_e_otto):
    """O que gravar no campo `autor` da mensagem da IA, no momento em que ela sai."""
    return OTTO if motor_e_otto else SEBASTIAO
