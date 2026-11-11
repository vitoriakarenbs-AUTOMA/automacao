# -*- coding: utf-8 -*-
"""O card anda sozinho quando a ligacao aconteceu (Pam, 15/10/2026).

A Rafa liga pelo WhatsApp de dentro do sistema, a ligacao fica gravada e transcrita
na conversa, e mesmo assim o card continua em "Caixa de Entrada GR". Em 15/10 havia
11 cards assim: trabalhados de verdade, invisiveis no quadro. A Rafa nao enxerga o
estagio, o painel conta errado e o lead corre o risco de ser abordado como se fosse
novo.

Esta rotina olha o FATO, nao o julgamento: se existe ligacao registrada na conversa,
o card sai da coluna de entrada e vai para "Ligacao feita, apresentacao enviada".

Nao e o --mover-card do pos_ligacao.py, que esta desligado desde 23/09 porque usa a
leitura da IA para decidir o desfecho e reclassificar o lead. Aqui nao ha julgamento
nenhum: ou a ligacao aconteceu, ou nao.

Tres travas:
  1. so mexe em card que esta na coluna de ENTRADA. Card que ja avancou fica onde esta,
     e nunca volta para tras;
  2. espera 30 minutos depois da ligacao, para dar a vez a quem quiser mover a mao;
  3. registra em wa_board_hist e deixa nota na conversa, para ninguem achar que o
     card andou sozinho sem motivo.

    python3 card_apos_ligacao.py             mostra o que faria
    python3 card_apos_ligacao.py --aplicar   move de verdade
"""
import argparse
import sqlite3
from datetime import datetime, timedelta, timezone

DB = '/opt/santoslourenco/SISTEMA/backend/sistema_sl.db'
BOARD = 24
DE = 'Caixa de Entrada GR'
PARA = 'Ligação feita · apresentação enviada'
ORIGEM = 'card_apos_ligacao'
FOLGA_MIN = 30          # tempo que a equipe tem para mover a mao antes de mim

# o que conta como "a ligacao aconteceu"
MARCAS = ('%TRANSCRICAO DA LIGACAO%', '%Gravacao da ligacao pelo WhatsApp%',
          '%de conversa, desligada%')


def achar(db):
    marcas = ' or '.join("m.conteudo like '%s'" % m for m in MARCAS)
    q = ("select v.id as id, coalesce(v.contato_nome,'') as nome, "
         "       max(m.criado_em) as quando, count(*) as quantas "
         "  from wa_conversas v join wa_mensagens m on m.conversa_id = v.id "
         " where v.pipeline_id = ? and v.etapa = ? and (%s) "
         " group by v.id order by v.id" % marcas)
    return db.execute(q, (BOARD, DE)).fetchall()


def mover(db, cid, agora):
    db.execute('update wa_conversas set etapa=?, atualizado_em=? where id=?',
               (PARA, agora, cid))
    db.execute('insert into wa_board_hist(conversa_id, de_pipeline, de_etapa, '
               'para_pipeline, para_etapa, quem, origem, bloqueado, criado_em) '
               'values(?,?,?,?,?,?,?,0,?)',
               (cid, BOARD, DE, BOARD, PARA, 'automacao', ORIGEM, agora))
    db.execute('insert into wa_mensagens(conversa_id, origem, autor, tipo, conteudo, '
               'midia_url, criado_em, remote_id) values(?,?,?,?,?,?,?,?)',
               (cid, 'nota', 'sistema', 'texto',
                'Card movido para "%s" porque a ligação já está registrada aqui na '
                'conversa. Se não for o caso, é só arrastar de volta.' % PARA,
                '', agora, ''))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--aplicar', action='store_true')
    ap.add_argument('--folga', type=int, default=FOLGA_MIN)
    a = ap.parse_args()

    db = sqlite3.connect(DB, timeout=30)
    db.execute('PRAGMA busy_timeout=30000')
    db.row_factory = sqlite3.Row
    corte = (datetime.now(timezone.utc) - timedelta(minutes=a.folga)).strftime('%Y-%m-%d %H:%M:%S')
    agora = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

    linhas = achar(db)
    print('cards em "%s" com ligação registrada: %d' % (DE, len(linhas)))
    movidos = esperando = 0
    for r in linhas:
        recente = (r['quando'] or '') > corte
        marca = 'aguarda a equipe' if recente else '-> %s' % PARA
        print('   #%-6s %-24s última ligação %s  %s'
              % (r['id'], (r['nome'] or 'sem nome')[:24], (r['quando'] or '')[:16], marca))
        if recente:
            esperando += 1
            continue
        if a.aplicar:
            mover(db, r['id'], agora)
        movidos += 1
    if a.aplicar:
        db.commit()
    db.close()
    print('\n%d movidos%s, %d ainda na folga de %d min'
          % (movidos, '' if a.aplicar else ' (simulação, nada gravado)', esperando, a.folga))


if __name__ == '__main__':
    main()
