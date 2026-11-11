#!/usr/bin/env python3
"""Espelho do ASTREA (10/11/2026). Cron sugerido: 30 5 * * *  (antes do expediente).

1. traz a carteira (processos/casos + clientes ligados) para o banco do sistema;
2. le os andamentos dos processos ATIVOS que tem vinculo com o Astrea;
3. reenvia tarefas e andamentos que nao subiram na hora (astrea_pendencias).

So roda com SISTEMA_JURIDICO=astrea e ASTREA_USUARIO/ASTREA_SENHA no config/.env.
Logica em SISTEMA/backend/app/astrea_sync.py; cliente em INTEGRACOES/astrea_client.py.

Uso: python3 SYNC/astrea_espelho.py [--ensaio] [--sem-andamentos]
     --ensaio: roda numa copia do banco em memoria e so mostra o que faria (nao envia nada)
"""
import datetime as dt
import sqlite3
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'SISTEMA' / 'backend'))
sys.path.insert(0, str(RAIZ / 'INTEGRACOES'))
from app import astrea_sync as AS  # noqa: E402

ENSAIO = '--ensaio' in sys.argv
SEM_ANDAMENTOS = '--sem-andamentos' in sys.argv


def main():
    agora = dt.datetime.now().strftime('%d/%m/%Y %H:%M')
    if not AS.ligado():
        print(agora, '| Astrea desligado (SISTEMA_JURIDICO/credencial): nada a fazer')
        return 0
    real = sqlite3.connect(AS.DB, timeout=30)
    if ENSAIO:
        c = sqlite3.connect(':memory:')
        real.backup(c)
        real.close()
    else:
        c = real
    c.row_factory = sqlite3.Row
    AS.garantir(c)
    a = AS.cliente()
    try:
        try:
            vistos = set()
            cart = AS.importar_carteira(c, a, vistos=vistos)
        except AS.FiltroErro as e:
            print(agora, '| NADA IMPORTADO:', e)
            return 1
        print(agora, '| carteira:', cart, '| ENSAIO' if ENSAIO else '')
        if not SEM_ANDAMENTOS:
            # so processos que passaram no filtro de responsaveis NESTA rodada
            ids = [r[0] for r in c.execute(
                "SELECT v.local_id, v.astrea_id FROM astrea_vinculos v JOIN jur_processos p ON p.id = v.local_id "
                "WHERE v.entidade='processo' AND p.encerrado=0") if r[1] in vistos]
            novos = falhas = 0
            for pid in ids:
                r = AS.sincronizar_andamentos(c, pid, a)
                if r is None:
                    falhas += 1
                else:
                    novos += r[0]
                time.sleep(0.4)          # ritmo de gente: nao martela o Astrea
            print('andamentos: %d processos lidos, %d andamentos novos, %d sem resposta' % (len(ids), novos, falhas))
        if ENSAIO:
            n = c.execute('SELECT COUNT(*) FROM astrea_pendencias').fetchone()[0]
            print('pendencias de envio (nao enviadas no ensaio): %d' % n)
        else:
            print('pendencias:', AS.reenviar_pendencias(c, a))
        return 0
    finally:
        c.close()


if __name__ == '__main__':
    sys.exit(main())
