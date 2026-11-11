# -*- coding: utf-8 -*-
"""Contra quem corre o caso de desbloqueio: a gerenciadora, a tomadora, ou as duas.

Spec: SISTEMA/docs/2026-11-07_contra_quem/SPEC_contra_quem.md
Decisões da Dra. Vitória em 07/11/2026.

POR QUE ESTE CAMPO EXISTE
O bloqueio do caminhoneiro nem sempre vem da gerenciadora de risco. No caso do Carlos Yoel
(card #3514), a gerenciadora dava o cadastro como "Conforme", e quem barrou foi a **tomadora
do serviço**, no portão do centro de distribuição. Nas palavras dele: *"eu agreguei meu
caminhão no transportador da Pandurata, que é da Pandurata mesmo"*, e a notificação servia
para *"comprovar que o meu bloqueio é uma arbitrariedade interna e exclusiva"* daquela
empresa.

A fundamentação, a notificação e o caminho são diferentes nos dois casos. O robô da produção
precisa saber disso desde a qualificação, e não pode errar.

O CONTRATO COM A CAIXA DO ROBÔ (SYNC/gr_producao.py, que não se mexe aqui)
- `wa_conversas.contra_quem`: 'gerenciadora' | 'tomadora' | 'ambas' | NULL
- `wa_conversas.tomadora_nome`: texto | NULL
- O robô lê as duas. Vazias, ele identifica e grava com origem 'robo'. Preenchidas e
  divergentes, ele **não troca**: abre tarefa para a Dra. Bruna decidir. `definir_pelo_robo`
  e `conferir_do_robo` existem para ele não precisar reescrever essa regra.
"""
import os
import re
import sqlite3
from datetime import datetime, timezone

GERENCIADORA, TOMADORA, AMBAS = 'gerenciadora', 'tomadora', 'ambas'
OPCOES = (GERENCIADORA, TOMADORA, AMBAS)

# Como a equipe lê na tela.
ROTULO = {
    GERENCIADORA: 'Gerenciadora de risco',
    TOMADORA: 'Tomadora do serviço (embarcador ou transportadora)',
    AMBAS: 'As duas',
}

# As opções em que a empresa tomadora precisa ser nomeada: sem o nome, a notificação não tem
# para quem ir (decisão 11.2).
EXIGEM_TOMADORA = (TOMADORA, AMBAS)

PRODUTO_GR = 'gr'

# O quadro da produção do GR. Fora dele, o caso ainda está na mão de quem vendeu.
QUADRO_PRODUCAO = 25

# Quem resolve a divergência, por configuração e não por nome no meio do código.
PRODUCAO_EMAIL = os.getenv('CONTRA_QUEM_PRODUCAO', 'operacional.bruna@sladvogados.com.br')
DISTRIBUI_EMAIL = os.getenv('CONTRA_QUEM_DISTRIBUI', 'vitoria.lourenco@sladvogados.com.br')


class ValorInvalido(ValueError):
    """Valor fora das três opções. Quebra cedo, em vez de gravar balde fantasma."""


class SemPermissao(PermissionError):
    """Quem não é admin nem vendedora tentou marcar."""


class ConflitoDeVersao(RuntimeError):
    """O campo mudou depois de a tela ler: outra pessoa marcou no meio."""


class SoParaDesbloqueio(ValueError):
    """Card que não é de GR. "Contra quem" num card de trabalhista é dado sem significado."""


class FaltaTomadora(ValueError):
    """Escolheu tomadora (ou as duas) e não disse qual empresa."""


def _agora():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def _limpar(texto):
    """O nome da empresa como a pessoa escreveu, sem espaço sobrando."""
    return re.sub(r'\s+', ' ', (texto or '').strip()) or None


def _tem_coluna(con, coluna):
    return any(c[1] == coluna for c in con.execute('pragma table_info(wa_conversas)'))


def criar_esquema(con):
    """As duas colunas, o histórico e o gatilho. Idempotente.

    O gatilho existe porque a trava tem de valer também para escrita feita por fora da API
    (script, esteira, SQL na mão), que é como três conversas se perderam em 03/11/2026.
    """
    for coluna in ('contra_quem', 'tomadora_nome'):
        if not _tem_coluna(con, coluna):
            con.execute('ALTER TABLE wa_conversas ADD COLUMN %s TEXT' % coluna)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS wa_contra_quem_hist (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          conversa_id INTEGER NOT NULL,
          de_valor TEXT, para_valor TEXT,
          de_tomadora TEXT, para_tomadora TEXT,
          quem TEXT NOT NULL,
          origem TEXT,
          bloqueado INTEGER DEFAULT 0,
          motivo TEXT,
          criado_em TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS ix_contra_quem_hist
          ON wa_contra_quem_hist (conversa_id, id DESC);
        CREATE INDEX IF NOT EXISTS ix_conversas_contra_quem
          ON wa_conversas (contra_quem);

        CREATE TRIGGER IF NOT EXISTS tg_contra_quem_valido_ins
        BEFORE INSERT ON wa_conversas
        WHEN NEW.contra_quem IS NOT NULL
         AND NEW.contra_quem NOT IN ('gerenciadora', 'tomadora', 'ambas')
        BEGIN
          SELECT RAISE(ABORT, 'contra_quem invalido: so gerenciadora, tomadora ou ambas');
        END;

        CREATE TRIGGER IF NOT EXISTS tg_contra_quem_valido_upd
        BEFORE UPDATE OF contra_quem ON wa_conversas
        WHEN NEW.contra_quem IS NOT NULL
         AND NEW.contra_quem NOT IN ('gerenciadora', 'tomadora', 'ambas')
        BEGIN
          SELECT RAISE(ABORT, 'contra_quem invalido: so gerenciadora, tomadora ou ambas');
        END;
    """)
    con.commit()


def pode_trocar(user):
    """As mesmas regras do campo Produto (decisão 4 da Pam): os dois admins e as duas
    comerciais. Uma regra só, num lugar só."""
    from . import produto_card
    return produto_card.pode_trocar_produto(user)


def _card(con, cid):
    r = con.execute("select coalesce(produto,''), coalesce(contra_quem,''), "
                    "coalesce(tomadora_nome,''), coalesce(atendente_email,''), "
                    "coalesce(pipeline_id,0) "
                    "from wa_conversas where id=?", (cid,)).fetchone()
    if not r:
        return None
    return {'produto': r[0] or None, 'contra_quem': r[1] or None,
            'tomadora_nome': r[2] or None, 'dona': r[3] or None,
            'quadro': int(r[4] or 0)}


def contra_quem_do_card(con, cid):
    """O que a tela precisa saber. `mostrar` diz se o campo aparece.

    Pam, 07/11/2026: "quando for trabalhista, a gente esconde o campo; o campo só vai abrir
    quando for GR". O valor NÃO é apagado quando o produto muda: se o card voltar para GR, a
    informação está lá, e o histórico mostra quem marcou.
    """
    c = _card(con, cid)
    if not c:
        return None
    return {'contra_quem': c['contra_quem'], 'tomadora_nome': c['tomadora_nome'],
            'mostrar': c['produto'] == PRODUTO_GR,
            'rotulo': ROTULO.get(c['contra_quem'], ''),
            'opcoes': [{'valor': v, 'rotulo': ROTULO[v]} for v in OPCOES],
            'exige_tomadora': c['contra_quem'] in EXIGEM_TOMADORA}


def _registrar(con, cid, de_v, para_v, de_t, para_t, quem, origem, bloqueado=0, motivo=''):
    con.execute(
        'INSERT INTO wa_contra_quem_hist (conversa_id, de_valor, para_valor, de_tomadora, '
        'para_tomadora, quem, origem, bloqueado, motivo, criado_em) '
        'VALUES (?,?,?,?,?,?,?,?,?,?)',
        (cid, de_v, para_v, de_t, para_t, quem, origem, 1 if bloqueado else 0,
         motivo or None, _agora()))


def _gravar(con, cid, valor, tomadora, c, quem, origem, motivo):
    try:
        con.execute('UPDATE wa_conversas SET contra_quem=?, tomadora_nome=? WHERE id=?',
                    (valor, tomadora, cid))
        _registrar(con, cid, c['contra_quem'], valor, c['tomadora_nome'], tomadora,
                   quem, origem, motivo=motivo)
        con.commit()
    except Exception:
        con.rollback()
        raise
    return valor


def definir(con, cid, valor, tomadora_nome, de_valor, user, motivo='', origem='ui'):
    """Marca contra quem o caso corre. Devolve o valor novo, ou None quando nada muda.

    Ordem das recusas, da mais barata para a mais cara: valor inválido (422), card que não é
    de GR (422), sem permissão (403, e a tentativa fica registrada), falta o nome da tomadora
    (422), e alguém trocou no meio (409). Em qualquer uma delas o card não é tocado.
    """
    if valor not in OPCOES:
        raise ValorInvalido('valor invalido: %r. Use um de %s' % (valor, list(OPCOES)))
    c = _card(con, cid)
    if not c or c['produto'] != PRODUTO_GR:
        raise SoParaDesbloqueio(
            'o card %r nao e de Desbloqueio em GR: marque o produto primeiro' % (cid,))

    quem = (getattr(user, 'email', '') or '?')
    if not pode_trocar(user):
        _registrar(con, cid, c['contra_quem'], valor, c['tomadora_nome'], None, quem,
                   origem, bloqueado=1, motivo=motivo or 'sem permissao')
        con.commit()
        raise SemPermissao('%s nao pode marcar contra quem corre este caso' % quem)

    tomadora = _limpar(tomadora_nome) if valor in EXIGEM_TOMADORA else None
    if valor in EXIGEM_TOMADORA and not tomadora:
        raise FaltaTomadora(
            'escolhendo %r e preciso dizer qual empresa barrou, com a unidade '
            '(ex.: "Pandurata, CD de Extrema/MG")' % valor)

    if (c['contra_quem'] or None) != (de_valor or None):
        raise ConflitoDeVersao(
            'este card agora esta como %r, e nao %r: outra pessoa marcou no meio. '
            'Recarregue o card e tente de novo.' % (c['contra_quem'], de_valor))

    if c['contra_quem'] == valor and c['tomadora_nome'] == tomadora:
        return None                      # nada mudou: nao vira registro

    return _gravar(con, cid, valor, tomadora, c, quem, origem, motivo)


# --------------------------------------------------------------------------- o robô

def definir_pelo_robo(con, cid, valor, tomadora_nome, motivo=''):
    """O robô da produção preenche o que está vazio. NUNCA sobrescreve o que uma pessoa marcou.

    Quando discorda, ele não troca: usa `conferir_do_robo` e abre tarefa para a Dra. Bruna.
    """
    if valor not in OPCOES:
        raise ValorInvalido('valor invalido: %r' % (valor,))
    c = _card(con, cid)
    if not c or c['produto'] != PRODUTO_GR or c['contra_quem']:
        return None
    tomadora = _limpar(tomadora_nome) if valor in EXIGEM_TOMADORA else None
    return _gravar(con, cid, valor, tomadora, c, 'robo', 'robo',
                   motivo or 'identificado pela conversa')


def _e_vendedora(email):
    """Quem vende, e por isso pode marcar o campo e resolver a divergência."""
    from . import produto_card
    return (email or '').strip().lower() in produto_card.VENDEDORAS_PRODUTO


def quem_resolve(con, cid, de_producao=None):
    """Para quem vai a tarefa quando o robô discorda do que está marcado.

    Dra. Vitória, 07/11/2026: *"as tarefas são criadas para a vendedora mesmo ajustar. Só vai
    para Bruna quando for parte de produção."*

    Então o destino sai do estado do caso, e não de uma pessoa fixa:
    - caso já na produção do GR (quadro 25), ou assunto que o robô marca como de produção:
      vai para a produção, porque a peça e a notificação são dela;
    - caso ainda com quem vendeu: vai para a vendedora dona do card, que é quem ajusta;
    - card sem dona, ou com dona que não pode marcar o campo: vai para distribuir, porque
      tarefa que cai em quem não pode resolver é tarefa perdida.

    `de_producao=True` ou `False` deixa o robô decidir quando o quadro não conta a história;
    `None` (o padrão) decide pelo quadro.
    """
    c = _card(con, cid)
    if not c:
        return None
    da_producao = (c['quadro'] == QUADRO_PRODUCAO) if de_producao is None else bool(de_producao)
    if da_producao:
        return {'quem': PRODUCAO_EMAIL, 'papel': 'producao',
                'por_que': 'o caso esta na producao do GR, e a peca e a notificacao sao dela'}
    dona = (c['dona'] or '').strip().lower() or None
    if dona and _e_vendedora(dona):
        return {'quem': dona, 'papel': 'vendedora',
                'por_que': 'o card e da vendedora que atende, e e ela quem ajusta'}
    return {'quem': DISTRIBUI_EMAIL, 'papel': 'distribuir',
            'por_que': 'o card nao esta com uma vendedora que possa marcar o campo'}


def conferir_do_robo(con, cid, valor, tomadora_nome=None, de_producao=None):
    """O que o robô leu bate com o que está no card? Ele decide o que fazer com a resposta."""
    c = _card(con, cid)
    if not c:
        return {'divergente': False, 'no_card': None, 'o_robo_leu': valor, 'existe': False}
    divergente = bool(c['contra_quem']) and c['contra_quem'] != valor
    return {'divergente': divergente, 'no_card': c['contra_quem'], 'o_robo_leu': valor,
            'tomadora_no_card': c['tomadora_nome'], 'tomadora_do_robo': _limpar(tomadora_nome),
            'existe': True,
            'quem_resolve': quem_resolve(con, cid, de_producao) if divergente else None,
            'aviso': ('O card esta como %r e o robo leu %r na conversa. Decidir antes de '
                      'notificar.' % (ROTULO.get(c['contra_quem'], c['contra_quem']),
                                      ROTULO.get(valor, valor))) if divergente else ''}


def historico(con, cid):
    """As marcações deste card, da mais recente para a mais antiga."""
    try:
        linhas = con.execute(
            'select id, de_valor, para_valor, de_tomadora, para_tomadora, quem, origem, '
            'coalesce(bloqueado,0), motivo, criado_em from wa_contra_quem_hist '
            'where conversa_id=? order by id desc', (cid,)).fetchall()
    except sqlite3.Error:
        return []
    return [{'id': r[0], 'de_valor': r[1], 'para_valor': r[2], 'de_tomadora': r[3],
             'para_tomadora': r[4], 'quem': r[5], 'origem': r[6], 'bloqueado': bool(r[7]),
             'motivo': r[8], 'criado_em': r[9]} for r in linhas]
